@echo off
chcp 65001 >nul
title Antigravity - Сброс кэша и сессий
cls
echo ======================================================================
echo              СБРОС КЭША И СЕССИЙ ANTIGRAVITY
echo ======================================================================
echo.
echo Данный скрипт завершит процессы Antigravity и очистит временные файлы
echo кэша и старых токенов, если вы получаете вечную ошибку 400 / 403.
echo.
set /p CONFIRM="Вы уверены, что хотите продолжить? (Y/N): "
if /I not "%CONFIRM%"=="Y" (
    echo Отмена операции.
    pause
    exit /b
)

echo.
echo [1/3] Завершение процессов Antigravity...
taskkill /F /IM "Antigravity.exe" 2>nul
taskkill /F /IM "antigravity" 2>nul
taskkill /F /IM "code.exe" 2>nul
timeout /t 2 /nobreak >nul

echo [2/3] Очистка кэша в AppData...
if exist "%APPDATA%\Antigravity\Cache" (
    rmdir /S /Q "%APPDATA%\Antigravity\Cache" 2>nul
    echo   [OK] Очищен %APPDATA%\Antigravity\Cache
)
if exist "%APPDATA%\Antigravity\Code Cache" (
    rmdir /S /Q "%APPDATA%\Antigravity\Code Cache" 2>nul
    echo   [OK] Очищен %APPDATA%\Antigravity\Code Cache
)
if exist "%APPDATA%\Antigravity\GPUCache" (
    rmdir /S /Q "%APPDATA%\Antigravity\GPUCache" 2>nul
    echo   [OK] Очищен %APPDATA%\Antigravity\GPUCache
)

echo [3/3] Очистка временных токенов сервиса Gemini...
if exist "%USERPROFILE%\.gemini\antigravity\auth_cache.json" (
    del /F /Q "%USERPROFILE%\.gemini\antigravity\auth_cache.json" 2>nul
    echo   [OK] Удален старый auth_cache.json
)

echo.
echo ======================================================================
echo Очистка завершена! 
echo Теперь:
echo 1. Убедитесь, что zapret и Antigravity Unlocker 2 запущены.
echo 2. Запустите Antigravity и повторите вход в аккаунт.
echo ======================================================================
echo.
pause
