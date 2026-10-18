@echo off
chcp 65001 >nul
title Antigravity - Полный сброс кэша, сессий и служб
cls
echo ======================================================================
echo          ПОЛНЫЙ СБРОС КЭША, ТОКЕНОВ, СЕССИЙ И СЛУЖБ ANTIGRAVITY
echo ======================================================================
echo.
echo Данный скрипт:
echo 1. Завершит зависшие процессы Antigravity, language_server и ag_dns.
echo 2. Очистит кэш браузерного движка (GPUCache, Code Cache, IndexedDB)
echo    для устранения ЧЕРНОГО ЭКРАНА и зависаний.
echo 3. Сбросит битые региональные токены сессий (ошибка 400 и Model unavailable).
echo 4. Очистит кэш DNS Windows.
echo.
set /p CONFIRM="Вы уверены, что хотите продолжить? (Y/N): "
if /I not "%CONFIRM%"=="Y" (
    echo Отмена операции.
    pause
    exit /b
)

echo.
echo [1/5] Завершение процессов Antigravity, Language Server и DNS-служб...
taskkill /F /IM "Antigravity.exe" 2>nul
taskkill /F /IM "antigravity" 2>nul
taskkill /F /IM "Antigravity IDE.exe" 2>nul
taskkill /F /IM "code.exe" 2>nul
taskkill /F /IM "language_server.exe" 2>nul
taskkill /F /IM "ag_dns.exe" 2>nul
timeout /t 2 /nobreak >nul

echo [2/5] Очистка кэша в AppData\Roaming (2.0 и IDE)...
for %%P in ("Antigravity" "Antigravity IDE") do (
    if exist "%APPDATA%\%%~P\Cache" rmdir /S /Q "%APPDATA%\%%~P\Cache" 2>nul
    if exist "%APPDATA%\%%~P\Code Cache" rmdir /S /Q "%APPDATA%\%%~P\Code Cache" 2>nul
    if exist "%APPDATA%\%%~P\GPUCache" rmdir /S /Q "%APPDATA%\%%~P\GPUCache" 2>nul
    if exist "%APPDATA%\%%~P\IndexedDB" rmdir /S /Q "%APPDATA%\%%~P\IndexedDB" 2>nul
    if exist "%APPDATA%\%%~P\Session Storage" rmdir /S /Q "%APPDATA%\%%~P\Session Storage" 2>nul
)
echo   [OK] Очищены кэш, GPUCache и Session Storage в Roaming.

echo [3/5] Очистка кэша в AppData\Local...
for %%P in ("Antigravity" "Antigravity IDE" "antigravity") do (
    if exist "%LOCALAPPDATA%\%%~P\Cache" rmdir /S /Q "%LOCALAPPDATA%\%%~P\Cache" 2>nul
    if exist "%LOCALAPPDATA%\%%~P\GPUCache" rmdir /S /Q "%LOCALAPPDATA%\%%~P\GPUCache" 2>nul
    if exist "%LOCALAPPDATA%\%%~P\logs" rmdir /S /Q "%LOCALAPPDATA%\%%~P\logs" 2>nul
)
echo   [OK] Очищены LocalAppData кэш и логи.

echo [4/5] Очистка временных токенов и региональных привязок...
if exist "%USERPROFILE%\.gemini\antigravity\auth_cache.json" (
    del /F /Q "%USERPROFILE%\.gemini\antigravity\auth_cache.json" 2>nul
    echo   [OK] Удален старый auth_cache.json
)
if exist "%USERPROFILE%\.gemini\antigravity\session.json" (
    del /F /Q "%USERPROFILE%\.gemini\antigravity\session.json" 2>nul
    echo   [OK] Удален старый session.json
)

echo [5/5] Сброс системного кэша DNS Windows...
ipconfig /flushdns >nul
powershell -NoProfile -Command "Clear-DnsClientCache" 2>nul
echo   [OK] Системный DNS-кэш успешно очищен.

echo.
echo ======================================================================
echo Очистка успешно завершена! 
echo Теперь:
echo 1. Запустите zapret (от имени Администратора).
echo 2. Запустите Antigravity Unlocker 2 (от имени Администратора).
echo 3. Запустите Antigravity (2.0 или IDE) и выполните чистый вход.
echo ======================================================================
echo.
pause
