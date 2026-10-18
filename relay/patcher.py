#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NovaAntigravity Client Patcher v1.0.0
Safely patches Antigravity IDE to bypass onboarding / tier restrictions and gates.
Includes 100% safe restore/unpatch capability from original backups.
"""

import os
import sys
import re
import shutil
import argparse

VERSION = "1.0.0"

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
DIM = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"

MARKER_START = "/* NOVA_PATCH_START */"
MARKER_END = "/* NOVA_PATCH_END */"

def find_ide_paths():
    """Finds possible Antigravity IDE installation paths."""
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Antigravity IDE\resources\app\out\main.js"),
        os.path.expandvars(r"%PROGRAMFILES%\Antigravity IDE\resources\app\out\main.js"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\antigravity\resources\app\out\main.js"),
    ]
    found = []
    for c in candidates:
        if os.path.exists(c) or os.path.exists(c + ".ag_backup"):
            found.append(c)
    return found

def get_status(main_js_path: str) -> str:
    """Checks if main.js is patched, original, or missing."""
    if not os.path.exists(main_js_path):
        return "not_found"
    try:
        with open(main_js_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if MARKER_START in content or "userTier: { id: \"pro\"" in content or "userTier:{id:\"pro\"" in content:
            return "patched"
        return "original"
    except Exception:
        return "error"

def patch_file(main_js_path: str) -> bool:
    """Applies the safe onboarding bypass patch to main.js."""
    if not os.path.exists(main_js_path):
        print(f"{RED}[ERROR] File not found: {main_js_path}{RESET}")
        return False

    backup_path = main_js_path + ".ag_backup"
    if not os.path.exists(backup_path):
        print(f"{CYAN}[BACKUP] Creating original backup: {backup_path}{RESET}")
        shutil.copy2(main_js_path, backup_path)
    else:
        print(f"{DIM}[INFO] Backup already exists at: {backup_path}{RESET}")

    # Always read from backup to ensure clean base patch
    with open(backup_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Search for confirmUserForService method
    pattern = r'(async confirmUserForService\(t\)\{)(.*?)(\blet r;try\{if\(r=await this\._cloudCodeMainService\.loadCodeAssist\(t\))'
    m = re.search(pattern, content)
    if not m:
        print(f"{RED}[ERROR] Signature for confirmUserForService not found in main.js.{RESET}")
        return False

    prefix = m.group(1)
    body = m.group(2)
    suffix = m.group(3)

    # Extract dynamic state mapper helper function name (e.g. 'eve(t)')
    eve_match = re.search(r',a=([a-zA-Z0-9_$]+)\(t\);', body)
    eve_call = f"{eve_match.group(1)}(t)" if eve_match else "t"

    patch_code = f"""{MARKER_START}
    this._authActor.send({{type:t.isGcpTos?"GCP_SIGN_IN":"SIGN_IN"}});
    this._cloudCodeMainService.resetIsTierGCPTos();
    try {{
        try {{ await this._cloudCodeMainService.loadCodeAssist(t); }} catch(_) {{}}
        try {{ await this._cloudCodeMainService.onboardUser("standard-tier", t); }} catch(_) {{
            try {{ await this._cloudCodeMainService.onboardUser("free-tier", t); }} catch(__) {{}}
        }}
        let __res = {{ settings: {{}}, userTier: {{ id: "pro", description: "Pro" }} }};
        try {{ __res = await this.refreshUserStatus(t); }} catch(_) {{}}
        const a = {eve_call};
        try {{ this._unifiedStateSyncMainService.pushUpdate(a); }} catch(_) {{}}
        this._authActor.send({{type:"AUTH_SUCCESS",tokenInfo:t}});
        this._onDidOnboardUser.fire({{settings:__res.settings, userTier:__res.userTier}});
    }} catch(e) {{}}
    return;
{MARKER_END}
"""

    patched_content = content[:m.start()] + prefix + patch_code + suffix + content[m.end():]

    try:
        with open(main_js_path, "w", encoding="utf-8") as f:
            f.write(patched_content)
        print(f"{GREEN}[SUCCESS] Patch applied successfully to:{RESET} {main_js_path}")
        return True
    except Exception as e:
        print(f"{RED}[ERROR] Failed to write patched main.js: {e}{RESET}")
        return False

def restore_file(main_js_path: str) -> bool:
    """Restores main.js from .ag_backup."""
    backup_path = main_js_path + ".ag_backup"
    if not os.path.exists(backup_path):
        print(f"{YELLOW}[WARN] Backup file not found: {backup_path}{RESET}")
        return False

    try:
        shutil.copy2(backup_path, main_js_path)
        print(f"{GREEN}[SUCCESS] Restored original main.js from backup.{RESET}")
        return True
    except Exception as e:
        print(f"{RED}[ERROR] Failed to restore file: {e}{RESET}")
        return False

def main():
    if os.name == 'nt':
        os.system('')

    parser = argparse.ArgumentParser(description=f"NovaAntigravity Client Patcher v{VERSION}")
    parser.add_argument("--patch", action="store_true", help="Apply client patch")
    parser.add_argument("--restore", action="store_true", help="Restore original file from backup")
    parser.add_argument("--status", action="store_true", help="Check current patch status")
    parser.add_argument("--path", default=None, help="Explicit path to main.js")
    args = parser.parse_args()

    paths = [args.path] if args.path else find_ide_paths()

    print(f"""{CYAN}{BOLD}=============================================================
   NovaAntigravity Client Patcher v{VERSION}
   Onboarding & Tier Unlocker for Antigravity IDE
============================================================={RESET}""")

    if not paths:
        print(f"{RED}[ERROR] Could not automatically locate Antigravity IDE main.js.{RESET}")
        print("Please specify the path manually with: python patcher.py --path <path_to_main.js>")
        sys.exit(1)

    target_path = paths[0]
    status = get_status(target_path)
    print(f"{BOLD}Target File:{RESET}   {target_path}")
    print(f"{BOLD}Current Status:{RESET} {GREEN + 'PATCHED' if status == 'patched' else YELLOW + 'ORIGINAL'}{RESET}\n")

    if args.restore:
        restore_file(target_path)
    elif args.patch:
        patch_file(target_path)
    elif args.status:
        pass
    else:
        # Interactive mode
        print("Choose an action:")
        print("  [1] Apply Patch (Bypass onboarding & activate Pro tier)")
        print("  [2] Restore Original (Remove patch from backup)")
        print("  [0] Exit")
        try:
            choice = input("\nEnter choice [1/2/0]: ").strip()
            if choice == "1":
                patch_file(target_path)
            elif choice == "2":
                restore_file(target_path)
        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    main()
