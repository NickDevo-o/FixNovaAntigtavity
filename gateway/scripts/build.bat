@echo off
chcp 65001 >nul
title Сборка Antigravity Gateway
cd /d "%~dp0\.."

echo ======================================================================
echo          СБОРКА ANTIGRAVITY GATEWAY / UNLOCKER NEXT (GO)
echo ======================================================================
echo.

where go >nul 2>nul
if not "%ERRORLEVEL%"=="0" (
    echo [!] Go не обнаружен в системном PATH.
    echo     Установите Go: winget install GoLang.Go или с https://go.dev/dl/
    echo     Либо запустите готовый скрипт без компиляции: python run_standalone.py
    echo.
    pause
    exit /b 1
)

echo [1/2] Компиляция легковесного бинарника...
set CGO_ENABLED=0
go build -ldflags="-s -w" -trimpath -o antigravity-gateway.exe ./cmd/gateway

if "%ERRORLEVEL%"=="0" (
    echo.
    echo ======================================================================
    echo [OK] Сборка успешно завершена! Создан файл: antigravity-gateway.exe
    echo ======================================================================
) else (
    echo [!] Ошибка во время сборки.
)

pause
