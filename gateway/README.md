# ⚡ Antigravity Gateway / Unlocker Next

**Открытый, сверхлегковесный шлюз-анлокер нового поколения для Google Antigravity и Gemini AI.**  
Разработан для прямой работы в связке с **zapret (DPI Bypass)** без шифрованных VPN-туннелей, с защитой от срывов стриминга и сбоев буфера.

---

## 🚀 Почему этот проект заменяет Unlocker 2?

| Проблема в Unlocker 2 | Решение в Antigravity Gateway (Unlocker Next) |
| :--- | :--- |
| **Вечный статус "Working" (15+ мин):** `tls_pump` сбрасывает данные без троттлинга на скорости >110 КБ/с, переполняя буфер HTTP/2 (`SETTINGS_INITIAL_WINDOW_SIZE` = 128 КиБ) и вызывая кулдаун Google на 2–10 мин. | **Flow-Controlled Stream Pump:** Динамический контроль размера окна и микро-пейсинг на контекстах >100 КиБ. Полная защита от `FLOW_CONTROL_ERROR` и разрывов TCP RST. |
| **Зависающий сервис `ag_dns.exe`:** Служба DNS регулярно падает, блокирует сокет и не чинится кнопкой «Починить». | **Встроенный DoH (DNS-over-HTTPS):** Прямой резолв через Cloudflare (`1.1.1.1`) и Google (`8.8.8.8`) прямо внутри процесса с кэшированием в RAM. Внешние службы и драйверы не нужны! |
| **Ошибка `os error 10061 (Подключение отвергнуто)`:** Возникает при недоступности локального или стороннего прокси на 10809. | **Graceful Failover:** При недоступности апстрима шлюз не крашится, а автоматически мягко переключается на прямой zapret-маршрут. |
| **Ошибка `Agent execution terminated` в новых чатах:** Вызвана зависшими `language_server.exe` от старых сессий. | **Встроенный Process Manager:** Автоматически находит и завершает «осиротевшие» процессы перед стартом. |
| **Черный экран IDE:** Повреждение кэша рендера Chromium/Electron. | **Встроенный Cache Cleaner:** Очистка `GPUCache` и `Code Cache` в один клик клавишей `[C]`. |
| **Закрытый код и детекты антивирусов:** Обфусцированный закрытый софт триггерит Windows Defender. | **100% Open Source:** Прозрачный чистый код без сторонних подозрительных DLL и троянов. |

---

## 🛠️ Структура проекта

```
gateway/
├── cmd/
│   └── gateway/
│       └── main.go           # CLI-интерфейс, обработчик сигналов и интерактивные хоткеи
├── internal/
│   ├── config/
│   │   └── config.go         # Загрузчик конфигурации (JSON / YAML)
│   ├── doh/
│   │   └── doh.go            # Встроенный DoH клиент с кэшированием в памяти
│   ├── stream/
│   │   └── stream.go         # Flow-Control релей с защитой от 128 КиБ переполнения
│   ├── proxy/
│   │   ├── headers.go        # Очистка и нормализация гео-заголовков
│   │   ├── tunnel.go         # HTTP CONNECT туннелирование с zapret-direct / failover
│   │   └── server.go         # Сервер прокси с автоподбором портов (10809-10820)
│   └── cleaner/
│       ├── cache.go          # Очистка GPUCache и сброс битых токенов
│       ├── patcher.go        # Автопатч settings.json в профилях Antigravity
│       ├── process.go        # Завершение зависших language_server и сброс DNS
│       └── warmup.go         # Прогрев сокета Google AI и проверка задержки
├── scripts/
│   ├── build.bat             # Сборка одного бинарника antigravity-gateway.exe
│   └── run.bat               # Запуск скомпилированного .exe или Python-версии
├── config.json               # Конфигурация по умолчанию (JSON)
├── config.yaml               # Конфигурация по умолчанию (YAML)
├── go.mod                    # Определение Go модуля
└── run_standalone.py         # Полный автономный аналог на Python 3 (работает без установки Go)
```

---

## ⚡ Быстрый старт

### Вариант 1: Запуск прямо сейчас через Python (без компиляции)
Если у вас установлен Python 3.8+ (не требует сторонних библиотек `pip`):
```cmd
python gateway\run_standalone.py
```
или просто запустите `gateway\scripts\run.bat`.

### Вариант 2: Сборка в один автономный `.exe` файл (Go)
Если у вас установлен Go (`winget install GoLang.Go`):
```cmd
gateway\scripts\build.bat
```
В результате будет создан легковесный файл `antigravity-gateway.exe` (~6 МБ), который не требует внешних библиотек и готов к работе на любой Windows машине.

---

## 🎮 Интерактивные горячие клавиши (в консоли)

| Клавиша | Действие |
| :---: | :--- |
| **`[R]`** | Мгновенный сброс DoH-кэша шлюза и системного кэша DNS Windows (`ipconfig /flushdns`). |
| **`[C]`** | Очистка GPUCache (лечит черный экран) и перезапуск зависших `language_server.exe`. |
| **`[W]`** | Отправка тестового пинга на Google AI сокет с выводом задержки (Warmup / прогрев сокета). |
| **`[Q]`** | Корректное завершение работы шлюза с закрытием сокетов. |

---

## ⚙️ Конфигурация (`config.yaml` / `config.json`)

```yaml
server:
  host: "127.0.0.1"
  port: 10809
  auto_port: true # Автоподбор соседнего порта (10810..10820), если 10809 занят

upstream:
  mode: "direct" # "direct" (для zapret) или "proxy" (для своего VLESS/Clash/Xray)
  proxy_url: "" # Например: "socks5://127.0.0.1:10808"
  fallback_to_direct: true # Если прокси упал, автоматически идти напрямую через zapret

dns:
  enabled: true
  provider: "cloudflare" # DoH через 1.1.1.1 и dns.google

stream:
  enable_throttling: true # Предотвращает разрыв HTTP/2 сессии на запросах >128 КиБ
  throttle_threshold_kb: 120
  warn_payload_size_kb: 100
```
