package cleaner

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
)

// CleanAntigravityCache cleans GPUCache, Code Cache, and temporary locks
func CleanAntigravityCache(fullReset bool) (int, error) {
	cleaned := 0
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return 0, err
	}

	var candidateDirs []string

	if runtime.GOOS == "windows" {
		appData := os.Getenv("APPDATA")
		localAppData := os.Getenv("LOCALAPPDATA")

		for _, name := range []string{"Antigravity", "Antigravity IDE", "antigravity"} {
			if appData != "" {
				candidateDirs = append(candidateDirs,
					filepath.Join(appData, name, "GPUCache"),
					filepath.Join(appData, name, "Code Cache"),
				)
			}
			if localAppData != "" {
				candidateDirs = append(candidateDirs,
					filepath.Join(localAppData, name, "GPUCache"),
					filepath.Join(localAppData, name, "Code Cache"),
					filepath.Join(localAppData, name, "logs"),
				)
			}
		}

		if fullReset {
			geminiDir := filepath.Join(homeDir, ".gemini", "antigravity")
			_ = os.Remove(filepath.Join(geminiDir, "auth_cache.json"))
			_ = os.Remove(filepath.Join(geminiDir, "session.json"))
			cleaned++
		}
	} else if runtime.GOOS == "darwin" {
		appSupport := filepath.Join(homeDir, "Library", "Application Support")
		for _, name := range []string{"Antigravity", "Antigravity IDE"} {
			candidateDirs = append(candidateDirs,
				filepath.Join(appSupport, name, "GPUCache"),
				filepath.Join(appSupport, name, "Code Cache"),
			)
		}

		if fullReset {
			geminiDir := filepath.Join(homeDir, ".gemini", "antigravity")
			_ = os.Remove(filepath.Join(geminiDir, "auth_cache.json"))
			_ = os.Remove(filepath.Join(geminiDir, "session.json"))
			cleaned++
		}
	}

	for _, dir := range candidateDirs {
		if _, err := os.Stat(dir); err == nil {
			if err := os.RemoveAll(dir); err == nil {
				cleaned++
			}
		}
	}

	return cleaned, nil
}
