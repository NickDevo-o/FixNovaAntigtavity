@echo off
chcp 65001 >nul
title Restore Antigravity IDE

python "%~dp0patcher.py" --restore
echo.
pause
