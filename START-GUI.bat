@echo off
cd /d "%~dp0"
start "" pythonw gui.py
if %errorlevel% neq 0 (
    start "" python gui.py
)
exit /b 0
