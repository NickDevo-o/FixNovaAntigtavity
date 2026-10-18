package cleaner

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
)

const (
	NovaPatchStart = "/* NOVA_PATCH_START */"
	NovaPatchEnd   = "/* NOVA_PATCH_END */"
)

// FindMainJSPaths locates possible main.js files for Antigravity IDE
func FindMainJSPaths() []string {
	var candidates []string
	if runtime.GOOS == "windows" {
		localApp := os.Getenv("LOCALAPPDATA")
		progFiles := os.Getenv("ProgramFiles")
		if localApp != "" {
			candidates = append(candidates,
				filepath.Join(localApp, "Programs", "Antigravity IDE", "resources", "app", "out", "main.js"),
				filepath.Join(localApp, "Programs", "antigravity", "resources", "app", "out", "main.js"),
			)
		}
		if progFiles != "" {
			candidates = append(candidates,
				filepath.Join(progFiles, "Antigravity IDE", "resources", "app", "out", "main.js"),
			)
		}
	} else if runtime.GOOS == "darwin" {
		candidates = append(candidates,
			"/Applications/Antigravity IDE.app/Contents/Resources/app/out/main.js",
			"/Applications/Antigravity.app/Contents/Resources/app/out/main.js",
		)
	}

	var found []string
	for _, c := range candidates {
		if _, err := os.Stat(c); err == nil {
			found = append(found, c)
		} else if _, err := os.Stat(c + ".ag_backup"); err == nil {
			found = append(found, c)
		}
	}
	return found
}

// CheckMainJSPatched returns true if main.js is already patched
func CheckMainJSPatched(mainJSPath string) bool {
	content, err := os.ReadFile(mainJSPath)
	if err != nil {
		return false
	}
	str := string(content)
	return strings.Contains(str, NovaPatchStart) || strings.Contains(str, `userTier: { id: "pro"`) || strings.Contains(str, `userTier:{id:"pro"`)
}

// PatchMainJS applies the onboarding and tier unlock patch to main.js
func PatchMainJS(mainJSPath string) error {
	backupPath := mainJSPath + ".ag_backup"
	if _, err := os.Stat(backupPath); os.IsNotExist(err) {
		// Create backup
		orig, err := os.ReadFile(mainJSPath)
		if err != nil {
			return fmt.Errorf("failed to read original file: %w", err)
		}
		if err := os.WriteFile(backupPath, orig, 0644); err != nil {
			return fmt.Errorf("failed to create backup: %w", err)
		}
	}

	contentBytes, err := os.ReadFile(backupPath)
	if err != nil {
		return fmt.Errorf("failed to read backup: %w", err)
	}
	content := string(contentBytes)

	// Search for confirmUserForService method
	pattern := regexp.MustCompile(`(async confirmUserForService\(t\)\{)(.*?)(\blet r;try\{if\(r=await this\._cloudCodeMainService\.loadCodeAssist\(t\))`)
	loc := pattern.FindStringSubmatchIndex(content)
	if loc == nil {
		return fmt.Errorf("signature for confirmUserForService not found in main.js")
	}

	prefix := content[loc[2]:loc[3]]
	body := content[loc[4]:loc[5]]
	suffix := content[loc[6]:loc[7]]

	// Find dynamic state mapper (e.g. ,a=eve(t);)
	evePattern := regexp.MustCompile(`,a=([a-zA-Z0-9_$]+)\(t\);`)
	eveCall := "t"
	if eveMatch := evePattern.FindStringSubmatch(body); len(eveMatch) > 1 {
		eveCall = eveMatch[1] + "(t)"
	}

	patchCode := fmt.Sprintf(`%s
    this._authActor.send({type:t.isGcpTos?"GCP_SIGN_IN":"SIGN_IN"});
    this._cloudCodeMainService.resetIsTierGCPTos();
    try {
        try { await this._cloudCodeMainService.loadCodeAssist(t); } catch(_) {}
        try { await this._cloudCodeMainService.onboardUser("standard-tier", t); } catch(_) {
            try { await this._cloudCodeMainService.onboardUser("free-tier", t); } catch(__) {}
        }
        let __res = { settings: {}, userTier: { id: "pro", description: "Pro" } };
        try { __res = await this.refreshUserStatus(t); } catch(_) {}
        const a = %s;
        try { this._unifiedStateSyncMainService.pushUpdate(a); } catch(_) {}
        this._authActor.send({type:"AUTH_SUCCESS",tokenInfo:t});
        this._onDidOnboardUser.fire({settings:__res.settings, userTier:__res.userTier});
    } catch(e) {}
    return;
%s
`, NovaPatchStart, eveCall, NovaPatchEnd)

	patched := content[:loc[0]] + prefix + patchCode + suffix + content[loc[1]:]
	return os.WriteFile(mainJSPath, []byte(patched), 0644)
}

// RestoreMainJS restores original main.js from .ag_backup
func RestoreMainJS(mainJSPath string) error {
	backupPath := mainJSPath + ".ag_backup"
	if _, err := os.Stat(backupPath); os.IsNotExist(err) {
		return fmt.Errorf("backup file not found: %s", backupPath)
	}

	backupBytes, err := os.ReadFile(backupPath)
	if err != nil {
		return err
	}
	return os.WriteFile(mainJSPath, backupBytes, 0644)
}

// PatchAntigravitySettings configures http.proxy in Antigravity settings.json
func PatchAntigravitySettings(proxyPort int) ([]string, error) {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return nil, err
	}

	var targetFiles []string

	if runtime.GOOS == "windows" {
		appData := os.Getenv("APPDATA")
		if appData != "" {
			for _, app := range []string{"Antigravity", "Antigravity IDE", "antigravity"} {
				targetFiles = append(targetFiles, filepath.Join(appData, app, "User", "settings.json"))
			}
		}
	} else if runtime.GOOS == "darwin" {
		appSupport := filepath.Join(homeDir, "Library", "Application Support")
		for _, app := range []string{"Antigravity", "Antigravity IDE"} {
			targetFiles = append(targetFiles, filepath.Join(appSupport, app, "User", "settings.json"))
		}
	}

	proxyVal := fmt.Sprintf("http://127.0.0.1:%d", proxyPort)
	var patched []string

	for _, sf := range targetFiles {
		dir := filepath.Dir(sf)
		if _, err := os.Stat(dir); err != nil {
			continue // Parent folder doesn't exist, skip
		}

		settingsMap := make(map[string]interface{})
		if content, err := os.ReadFile(sf); err == nil && len(content) > 0 {
			_ = json.Unmarshal(content, &settingsMap)
		}

		settingsMap["http.proxy"] = proxyVal
		settingsMap["http.proxyStrictSSL"] = false
		settingsMap["http.proxySupport"] = "override"

		newContent, err := json.MarshalIndent(settingsMap, "", "  ")
		if err == nil {
			if writeErr := os.WriteFile(sf, newContent, 0644); writeErr == nil {
				patched = append(patched, sf)
			}
		}
	}

	return patched, nil
}

// UnpatchAntigravitySettings removes http.proxy from settings.json
func UnpatchAntigravitySettings() {
	homeDir, err := os.UserHomeDir()
	if err != nil {
		return
	}

	var targetFiles []string
	if runtime.GOOS == "windows" {
		appData := os.Getenv("APPDATA")
		if appData != "" {
			for _, app := range []string{"Antigravity", "Antigravity IDE", "antigravity"} {
				targetFiles = append(targetFiles, filepath.Join(appData, app, "User", "settings.json"))
			}
		}
	} else if runtime.GOOS == "darwin" {
		appSupport := filepath.Join(homeDir, "Library", "Application Support")
		for _, app := range []string{"Antigravity", "Antigravity IDE"} {
			targetFiles = append(targetFiles, filepath.Join(appSupport, app, "User", "settings.json"))
		}
	}

	for _, sf := range targetFiles {
		if content, err := os.ReadFile(sf); err == nil && len(content) > 0 {
			settingsMap := make(map[string]interface{})
			if jsonErr := json.Unmarshal(content, &settingsMap); jsonErr == nil {
				delete(settingsMap, "http.proxy")
				newContent, _ := json.MarshalIndent(settingsMap, "", "  ")
				_ = os.WriteFile(sf, newContent, 0644)
			}
		}
	}
}
