package cleaner

import (
	"fmt"
	"os/exec"
	"runtime"
	"strings"
)

// KillOrphanedProcesses terminates lingering language_server and ag_dns processes
func KillOrphanedProcesses() int {
	killed := 0
	targetProcesses := []string{"language_server", "ag_dns"}

	for _, proc := range targetProcesses {
		if runtime.GOOS == "windows" {
			cmd := exec.Command("taskkill", "/F", "/IM", proc+".exe")
			out, err := cmd.CombinedOutput()
			if err == nil && !strings.Contains(string(out), "не найден") && !strings.Contains(string(out), "not found") {
				killed++
			}
		} else {
			cmd := exec.Command("pkill", "-9", "-f", proc)
			if err := cmd.Run(); err == nil {
				killed++
			}
		}
	}

	return killed
}

// FlushSystemDNS clears the OS-level DNS cache
func FlushSystemDNS() error {
	if runtime.GOOS == "windows" {
		cmd := exec.Command("ipconfig", "/flushdns")
		return cmd.Run()
	} else if runtime.GOOS == "darwin" {
		cmd := exec.Command("dscacheutil", "-flushcache")
		return cmd.Run()
	}
	return nil
}
