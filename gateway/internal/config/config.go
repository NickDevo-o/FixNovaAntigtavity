package config

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type ServerConfig struct {
	Host     string `json:"host"`
	Port     int    `json:"port"`
	AutoPort bool   `json:"auto_port"`
}

type UpstreamConfig struct {
	Mode             string `json:"mode"`
	ProxyURL         string `json:"proxy_url"`
	FallbackToDirect bool   `json:"fallback_to_direct"`
	TimeoutSeconds   int    `json:"timeout_seconds"`
}

type DNSConfig struct {
	Enabled         bool     `json:"enabled"`
	Provider        string   `json:"provider"`
	CacheTTLMinutes int      `json:"cache_ttl_minutes"`
	CustomDoHURLs   []string `json:"custom_doh_urls"`
}

type StreamConfig struct {
	BufferSize          int  `json:"buffer_size"`
	EnableThrottling    bool `json:"enable_throttling"`
	ThrottleThresholdKB int  `json:"throttle_threshold_kb"`
	MaxRateKBps         int  `json:"max_rate_kbps"`
	WarnPayloadSizeKB   int  `json:"warn_payload_size_kb"`
	KeepAliveSeconds    int  `json:"keep_alive_seconds"`
}

type AntigravityConfig struct {
	AutoPatchSettings      bool `json:"auto_patch_settings"`
	AutoKillLanguageServer bool `json:"auto_kill_language_server"`
	WarmupOnStart          bool `json:"warmup_on_start"`
}

type LoggingConfig struct {
	Level string `json:"level"`
	Color bool   `json:"color"`
}

type Config struct {
	Server      ServerConfig      `json:"server"`
	Upstream    UpstreamConfig    `json:"upstream"`
	DNS         DNSConfig         `json:"dns"`
	Stream      StreamConfig      `json:"stream"`
	Antigravity AntigravityConfig `json:"antigravity"`
	Logging     LoggingConfig     `json:"logging"`
}

func DefaultConfig() *Config {
	return &Config{
		Server: ServerConfig{
			Host:     "127.0.0.1",
			Port:     10809,
			AutoPort: true,
		},
		Upstream: UpstreamConfig{
			Mode:             "direct",
			ProxyURL:         "",
			FallbackToDirect: true,
			TimeoutSeconds:   15,
		},
		DNS: DNSConfig{
			Enabled:         true,
			Provider:        "cloudflare",
			CacheTTLMinutes: 60,
			CustomDoHURLs: []string{
				"https://1.1.1.1/dns-query",
				"https://dns.google/resolve",
				"https://9.9.9.9/dns-query",
			},
		},
		Stream: StreamConfig{
			BufferSize:          16384,
			EnableThrottling:    true,
			ThrottleThresholdKB: 120,
			MaxRateKBps:         110,
			WarnPayloadSizeKB:   100,
			KeepAliveSeconds:    15,
		},
		Antigravity: AntigravityConfig{
			AutoPatchSettings:      true,
			AutoKillLanguageServer: true,
			WarmupOnStart:          true,
		},
		Logging: LoggingConfig{
			Level: "info",
			Color: true,
		},
	}
}

// LoadConfig attempts to find and load config.json or config.yaml from current dir or binary dir
func LoadConfig() (*Config, string, error) {
	cfg := DefaultConfig()

	candidatePaths := []string{
		"config.json",
		"config.yaml",
		"config.yml",
	}

	execPath, err := os.Executable()
	if err == nil {
		execDir := filepath.Dir(execPath)
		candidatePaths = append(candidatePaths,
			filepath.Join(execDir, "config.json"),
			filepath.Join(execDir, "config.yaml"),
		)
	}

	for _, path := range candidatePaths {
		if _, err := os.Stat(path); err == nil {
			content, readErr := os.ReadFile(path)
			if readErr != nil {
				continue
			}

			if strings.HasSuffix(strings.ToLower(path), ".json") {
				if err := json.Unmarshal(content, cfg); err == nil {
					return cfg, path, nil
				}
			} else {
				// Parse simple YAML or fallback
				parseSimpleYAML(string(content), cfg)
				return cfg, path, nil
			}
		}
	}

	return cfg, "defaults", nil
}

// parseSimpleYAML extracts primary config lines without requiring external third-party dependencies
func parseSimpleYAML(content string, cfg *Config) {
	lines := strings.Split(content, "\n")
	var section string

	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if len(trimmed) == 0 || strings.HasPrefix(trimmed, "#") {
			continue
		}

		if strings.HasSuffix(trimmed, ":") && !strings.Contains(trimmed, " ") {
			section = strings.TrimSuffix(trimmed, ":")
			continue
		}

		parts := strings.SplitN(trimmed, ":", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val := strings.TrimSpace(parts[1])
		val = strings.Trim(val, `"'`)
		// Remove inline comments
		if idx := strings.Index(val, "#"); idx != -1 {
			val = strings.TrimSpace(val[:idx])
			val = strings.Trim(val, `"'`)
		}

		switch section {
		case "server":
			switch key {
			case "host":
				cfg.Server.Host = val
			case "port":
				var p int
				if _, err := fmt.Sscanf(val, "%d", &p); err == nil && p > 0 {
					cfg.Server.Port = p
				}
			case "auto_port":
				cfg.Server.AutoPort = (val == "true" || val == "1")
			}
		case "upstream":
			switch key {
			case "mode":
				cfg.Upstream.Mode = val
			case "proxy_url":
				cfg.Upstream.ProxyURL = val
			case "fallback_to_direct":
				cfg.Upstream.FallbackToDirect = (val == "true" || val == "1")
			}
		case "dns":
			switch key {
			case "enabled":
				cfg.DNS.Enabled = (val == "true" || val == "1")
			case "provider":
				cfg.DNS.Provider = val
			}
		case "stream":
			switch key {
			case "enable_throttling":
				cfg.Stream.EnableThrottling = (val == "true" || val == "1")
			case "warn_payload_size_kb":
				var w int
				if _, err := fmt.Sscanf(val, "%d", &w); err == nil {
					cfg.Stream.WarnPayloadSizeKB = w
				}
			}
		}
	}
}
