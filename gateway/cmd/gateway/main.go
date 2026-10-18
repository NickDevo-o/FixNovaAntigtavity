package main

import (
	"bufio"
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/antigravity/gateway/internal/cleaner"
	"github.com/antigravity/gateway/internal/config"
	"github.com/antigravity/gateway/internal/doh"
	"github.com/antigravity/gateway/internal/proxy"
)

const Banner = `
  \033[36m   ___         __   _                      _ __         \033[0m
  \033[36m  / _ | ___   / /_ (_)__ _  _______ __  __(_) /___ __  \033[0m
  \033[36m / __ |/ _ \ / __// // _` + "`" + ` |/ __/ _` + "`" + ` \ \/ / / __/ // /  \033[0m
  \033[36m/_/ |_/_//_/ \__//_/ \__, /_/  \__,_/\_/_/_/\__/\_, /   \033[0m
  \033[36m                     /___/   \033[1;32mG A T E W A Y\033[0m\033[36m     /___/    \033[0m
  \033[90m========================================================\033[0m
  \033[1;37m Antigravity Gateway / Unlocker Next  •  v2.5.0-open\033[0m
  \033[90m Direct zapret-Bypass • Built-in DoH • Anti-Overflow 128K\033[0m
  \033[90m========================================================\033[0m
`

func printBanner() {
	// Simple color print
	colored := strings.ReplaceAll(Banner, `\033[36m`, "\033[36m")
	colored = strings.ReplaceAll(colored, `\033[0m`, "\033[0m")
	colored = strings.ReplaceAll(colored, `\033[90m`, "\033[90m")
	colored = strings.ReplaceAll(colored, `\033[1;32m`, "\033[1;32m")
	colored = strings.ReplaceAll(colored, `\033[1;37m`, "\033[1;37m")
	fmt.Println(colored)
}

func main() {
	portFlag := flag.Int("port", 0, "Local listen port (default from config: 10809)")
	modeFlag := flag.String("mode", "", "Routing mode: 'direct' (zapret) or 'proxy' (custom upstream)")
	upstreamFlag := flag.String("proxy", "", "Upstream proxy URL (e.g. socks5://127.0.0.1:10808)")
	cleanFlag := flag.Bool("clean", false, "Clean GPUCache and orphaned language_server processes and exit")
	resetFlag := flag.Bool("hard-reset", false, "Full reset of tokens (auth_cache.json) and cache then exit")
	warmupFlag := flag.Bool("warmup", false, "Run socket warmup probe and exit")
	patchFlag := flag.Bool("patch", false, "Apply onboarding & Pro tier unlock patch to main.js and exit")
	restoreFlag := flag.Bool("restore", false, "Restore original main.js from backup and exit")
	flag.Parse()

	// Handle quick CLI commands
	if *patchFlag {
		fmt.Println("🔧 Применение патча Antigravity IDE (обход онбординга и разблокировка Pro)...")
		paths := cleaner.FindMainJSPaths()
		if len(paths) == 0 {
			fmt.Println("❌ Не удалось найти main.js в стандартных путях.")
			return
		}
		for _, p := range paths {
			if err := cleaner.PatchMainJS(p); err != nil {
				fmt.Printf("❌ Ошибка патча %s: %v\n", p, err)
			} else {
				fmt.Printf("✔ Успешно пропатчен: %s\n", p)
			}
		}
		return
	}

	if *restoreFlag {
		fmt.Println("↩️  Восстановление оригинального main.js из бэкапа...")
		paths := cleaner.FindMainJSPaths()
		for _, p := range paths {
			if err := cleaner.RestoreMainJS(p); err != nil {
				fmt.Printf("❌ Ошибка отката %s: %v\n", p, err)
			} else {
				fmt.Printf("✔ Восстановлен оригинал: %s\n", p)
			}
		}
		return
	}

	if *cleanFlag {
		fmt.Println("🧹 Очистка кэша Antigravity и завершение language_server...")
		k := cleaner.KillOrphanedProcesses()
		c, _ := cleaner.CleanAntigravityCache(false)
		_ = cleaner.FlushSystemDNS()
		fmt.Printf("✔ Завершено процессов: %d, очищено каталогов: %d, DNS сброшен.\n", k, c)
		return
	}

	if *resetFlag {
		fmt.Println("⚠️  Полный сброс авторизации и кэша Antigravity...")
		k := cleaner.KillOrphanedProcesses()
		c, _ := cleaner.CleanAntigravityCache(true)
		_ = cleaner.FlushSystemDNS()
		fmt.Printf("✔ Завершено процессов: %d, удалено токенов и кэшей: %d.\n", k, c)
		return
	}

	printBanner()

	// 1. Load Configuration
	cfg, src, err := config.LoadConfig()
	if err != nil {
		fmt.Printf("⚠️ Ошибка загрузки конфига: %v. Используются значения по умолчанию.\n", err)
	} else {
		fmt.Printf("📋 Конфигурация: \033[36m%s\033[0m\n", src)
	}

	// Apply CLI overrides
	if *portFlag > 0 {
		cfg.Server.Port = *portFlag
	}
	if *modeFlag != "" {
		cfg.Upstream.Mode = *modeFlag
	}
	if *upstreamFlag != "" {
		cfg.Upstream.ProxyURL = *upstreamFlag
		cfg.Upstream.Mode = "proxy"
	}

	// 2. Kill orphaned language_server / ag_dns if enabled
	if cfg.Antigravity.AutoKillLanguageServer {
		killed := cleaner.KillOrphanedProcesses()
		if killed > 0 {
			fmt.Printf("🧹 Освобождены зависшие процессы: \033[33m%d\033[0m\n", killed)
		}
	}

	// 3. Initialize Built-in DoH
	dohResolver := doh.NewResolver(&cfg.DNS)
	if cfg.DNS.Enabled {
		fmt.Printf("🛡️  Встроенный DoH: \033[32mАКТИВЕН\033[0m (Cloudflare / Google, без внешнего ag_dns)\n")
	}

	// 4. Start Proxy Server
	srv := proxy.NewServer(cfg, dohResolver)
	activePort, err := srv.Start()
	if err != nil {
		fmt.Printf("\033[31m❌ Не удалось запустить сервер: %v\033[0m\n", err)
		os.Exit(1)
	}

	routeDesc := "\033[32mПрямое соединение (zapret WinDivert DPI Bypass)\033[0m"
	if cfg.Upstream.Mode == "proxy" {
		routeDesc = fmt.Sprintf("\033[33mUpstream: %s (с мягким Fallback на direct)\033[0m", cfg.Upstream.ProxyURL)
	}

	// Set environment variables for spawned IDE / language_server processes
	proxyURL := fmt.Sprintf("http://127.0.0.1:%d", activePort)
	_ = os.Setenv("AG_LS_PROXY", proxyURL)
	_ = os.Setenv("HTTP_PROXY", proxyURL)
	_ = os.Setenv("HTTPS_PROXY", proxyURL)

	fmt.Printf("⚡ Слушатель прокси: \033[1;32m%s\033[0m\n", proxyURL)
	fmt.Printf("🌐 Режим маршрутизации: %s\n", routeDesc)
	fmt.Printf("🌊 Flow-Control буфер: \033[32mВКЛЮЧЕН\033[0m (Защита от сброса HTTP/2 >128 КиБ)\n")
	fmt.Printf("🔗 Окружение: \033[36mAG_LS_PROXY=%s\033[0m\n", proxyURL)

	// 5. Auto-patch Antigravity settings if requested
	if cfg.Antigravity.AutoPatchSettings {
		patched, pErr := cleaner.PatchAntigravitySettings(activePort)
		if pErr == nil && len(patched) > 0 {
			fmt.Printf("🔧 Автопатч настроек: \033[32m%d файлов настроек обновлено\033[0m\n", len(patched))
		}
	}

	// 6. Warmup socket probe
	if cfg.Antigravity.WarmupOnStart || *warmupFlag {
		fmt.Print("⏳ Прогрев сокета Google AI... ")
		res := cleaner.WarmupGoogleSocket(activePort)
		if res.Success {
			fmt.Printf("\033[32mУСПЕШНО (%v, HTTP %d)\033[0m\n", res.Latency.Round(time.Millisecond), res.Status)
		} else {
			fmt.Printf("\033[33mПРЕДУПРЕЖДЕНИЕ (%v) - убедитесь, что zapret запущен!\033[0m\n", res.Error)
		}
		if *warmupFlag {
			return
		}
	}

	fmt.Println("\n\033[90m--------------------------------------------------------\033[0m")
	fmt.Println("Горячие клавиши:")
	fmt.Println("  [\033[1mR\033[0m] Сброс DNS-кэша  •  [\033[1mC\033[0m] Очистка GPUCache  •  [\033[1mW\033[0m] Тест связи  •  [\033[1mQ\033[0m] Выход")
	fmt.Println("\033[90m--------------------------------------------------------\033[0m\n")

	// Handle Interactive Hotkeys
	go func() {
		reader := bufio.NewReader(os.Stdin)
		for {
			input, err := reader.ReadString('\n')
			if err != nil {
				return
			}
			input = strings.TrimSpace(strings.ToUpper(input))

			switch input {
			case "R":
				cleared := dohResolver.FlushCache()
				_ = cleaner.FlushSystemDNS()
				fmt.Printf("\n\033[32m✔ Сброшен DoH кэш (%d записей) и системный DNS.\033[0m\n\n", cleared)
			case "C":
				k := cleaner.KillOrphanedProcesses()
				c, _ := cleaner.CleanAntigravityCache(false)
				fmt.Printf("\n\033[32m✔ GPUCache очищен (%d каталогов), завершено %d language_server.\033[0m\n\n", c, k)
			case "W":
				fmt.Print("\n⏳ Тестирование связи с Google... ")
				res := cleaner.WarmupGoogleSocket(activePort)
				if res.Success {
					fmt.Printf("\033[32mОК (%v, HTTP %d)\033[0m\n\n", res.Latency.Round(time.Millisecond), res.Status)
				} else {
					fmt.Printf("\033[31mОШИБКА: %v\033[0m\n\n", res.Error)
				}
			case "Q":
				fmt.Println("\nЗавершение работы...")
				_ = srv.Stop(context.Background())
				os.Exit(0)
			}
		}
	}()

	// Handle OS Signals (SIGINT, SIGTERM)
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, os.Interrupt, syscall.SIGTERM)
	<-sigCh

	fmt.Println("\n\nПолучен сигнал остановки. Завершение работы шлюза...")
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	_ = srv.Stop(shutdownCtx)
	fmt.Println("✔ Шлюз остановлен.")
}
