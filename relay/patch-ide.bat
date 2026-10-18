@echo off
chcp 65001 >nul
title Patch Antigravity IDE

python "%~dp0patcher.py" --patch
echo.
pause
