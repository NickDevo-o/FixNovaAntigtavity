@echo off
chcp 65001 >nul
title Antigravity Gateway
cd /d "%~dp0\.."

if exist "antigravity-gateway.exe" (
    antigravity-gateway.exe
) else (
    echo [i] Скомпилированный .exe не найден. Запуск через Python...
    where python >nul 2>nul
    if "%ERRORLEVEL%"=="0" (
        python run_standalone.py
    ) else (
        echo [!] Не найден ни antigravity-gateway.exe, ни Python!
        echo Запустите scripts\build.bat после установки Go.
        pause
    )
)
