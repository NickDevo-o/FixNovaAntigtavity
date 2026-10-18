@echo off
chcp 65001 >nul
title Antigravity - Полный сброс кэша и сессий
cls
echo ======================================================================
echo          ПОЛНЫЙ СБРОС КЭША, ТОКЕНОВ И СЕССИЙ ANTIGRAVITY
echo ======================================================================
echo.
echo Данный скрипт завершит процессы Antigravity и очистит временные файлы,
echo кэш сессий, IndexedDB и старые токены (аналог antigravity-cleaner).
echo Это решает проблемы с "залипанием" статуса Working, ошибкой 400 и 
echo ошибкой "Model is not available".
echo.
set /p CONFIRM="Вы уверены, что хотите продолжить? (Y/N): "
if /I not "%CONFIRM%"=="Y" (
    echo Отмена операции.
    pause
    exit /b
)

echo.
echo [1/4] Завершение процессов Antigravity...
taskkill /F /IM "Antigravity.exe" 2>nul
taskkill /F /IM "antigravity" 2>nul
taskkill /F /IM "code.exe" 2>nul
timeout /t 2 /nobreak >nul

echo [2/4] Очистка кэша в AppData\Roaming...
if exist "%APPDATA%\Antigravity\Cache" (
    rmdir /S /Q "%APPDATA%\Antigravity\Cache" 2>nul
    echo   [OK] Очищен Cache
)
if exist "%APPDATA%\Antigravity\Code Cache" (
    rmdir /S /Q "%APPDATA%\Antigravity\Code Cache" 2>nul
    echo   [OK] Очищен Code Cache
)
if exist "%APPDATA%\Antigravity\GPUCache" (
    rmdir /S /Q "%APPDATA%\Antigravity\GPUCache" 2>nul
    echo   [OK] Очищен GPUCache
)
if exist "%APPDATA%\Antigravity\IndexedDB" (
    rmdir /S /Q "%APPDATA%\Antigravity\IndexedDB" 2>nul
    echo   [OK] Очищен IndexedDB
)
if exist "%APPDATA%\Antigravity\Session Storage" (
    rmdir /S /Q "%APPDATA%\Antigravity\Session Storage" 2>nul
    echo   [OK] Очищен Session Storage
)

echo [3/4] Очистка кэша в AppData\Local...
if exist "%LOCALAPPDATA%\Antigravity\Cache" (
    rmdir /S /Q "%LOCALAPPDATA%\Antigravity\Cache" 2>nul
    echo   [OK] Очищен LocalAppData\Cache
)
if exist "%LOCALAPPDATA%\Antigravity\logs" (
    rmdir /S /Q "%LOCALAPPDATA%\Antigravity\logs" 2>nul
    echo   [OK] Очищены старые логи
)

echo [4/4] Очистка временных токенов и региональных привязок...
if exist "%USERPROFILE%\.gemini\antigravity\auth_cache.json" (
    del /F /Q "%USERPROFILE%\.gemini\antigravity\auth_cache.json" 2>nul
    echo   [OK] Удален старый auth_cache.json
)
if exist "%USERPROFILE%\.gemini\antigravity\session.json" (
    del /F /Q "%USERPROFILE%\.gemini\antigravity\session.json" 2>nul
    echo   [OK] Удален старый session.json
)

echo.
echo ======================================================================
echo Очистка успешно завершена! 
echo Теперь:
echo 1. Убедитесь, что zapret и Antigravity Unlocker 2 запущены (VPN ВЫКЛ!).
echo 2. Запустите Antigravity и выполните чистый вход.
echo ======================================================================
echo.
pause
