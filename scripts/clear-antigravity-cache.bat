@echo off
chcp 65001 >nul
title Antigravity - Очистка кэша и процессов
cls
echo ======================================================================
echo              ОЧИСТКА И ВОССТАНОВЛЕНИЕ ANTIGRAVITY
echo ======================================================================
echo.
echo Выберите режим очистки:
echo.
echo [1] БЕЗОПАСНАЯ ОЧИСТКА (Рекомендуется по умолчанию)
echo     - Устраняет ЧЕРНЫЙ ЭКРАН (очистка GPUCache и Code Cache).
echo     - Завершает зависшие процессы language_server.exe и ag_dns.exe.
echo     - Сбрасывает системный кэш DNS Windows.
echo     * ВАЖНО: НЕ разлогинивает вас и СОХРАНЯЕТ локальную историю чатов!
echo.
echo [2] ПОЛНЫЙ СБРОС ТОКЕНОВ И СЕССИЙ (Крайняя мера)
echo     - Применяется ТОЛЬКО если у вас вечная ошибка 400 / бан региона.
echo     - Удаляет auth_cache.json, session.json и IndexedDB.
echo     * ВНИМАНИЕ: Потребуется повторный вход в аккаунт Google!
echo.
echo [0] Выход
echo.
set /p MODE="Введите номер режима [1, 2 или 0]: "

if "%MODE%"=="0" exit /b
if "%MODE%"=="1" goto SOFT_CLEAN
if "%MODE%"=="2" goto HARD_CLEAN

echo Неверный выбор!
pause
exit /b

:SOFT_CLEAN
echo.
echo [1/3] Завершение зависших процессов Antigravity и Language Server...
taskkill /F /IM "Antigravity.exe" 2>nul
taskkill /F /IM "antigravity" 2>nul
taskkill /F /IM "Antigravity IDE.exe" 2>nul
taskkill /F /IM "code.exe" 2>nul
taskkill /F /IM "language_server.exe" 2>nul
taskkill /F /IM "ag_dns.exe" 2>nul
timeout /t 2 /nobreak >nul

echo [2/3] Очистка кэша рендера (GPUCache, Code Cache)...
for %%P in ("Antigravity" "Antigravity IDE" "antigravity") do (
    if exist "%APPDATA%\%%~P\GPUCache" rmdir /S /Q "%APPDATA%\%%~P\GPUCache" 2>nul
    if exist "%APPDATA%\%%~P\Code Cache" rmdir /S /Q "%APPDATA%\%%~P\Code Cache" 2>nul
    if exist "%LOCALAPPDATA%\%%~P\GPUCache" rmdir /S /Q "%LOCALAPPDATA%\%%~P\GPUCache" 2>nul
    if exist "%LOCALAPPDATA%\%%~P\logs" rmdir /S /Q "%LOCALAPPDATA%\%%~P\logs" 2>nul
)
echo   [OK] GPU-кэш очищен (черный экран устранен).

echo [3/3] Сброс кэша DNS...
ipconfig /flushdns >nul
powershell -NoProfile -Command "Clear-DnsClientCache" 2>nul
echo   [OK] DNS-кэш очищен.

echo.
echo ======================================================================
echo Безопасная очистка завершена! Ваши сессии и чаты на месте.
echo Запустите zapret, Unlocker и Antigravity.
echo ======================================================================
echo.
pause
exit /b

:HARD_CLEAN
echo.
echo ВНИМАНИЕ: Будет выполнен полный сброс авторизации и локальных токенов.
set /p CONFIRM="Вы уверены? (Y/N): "
if /I not "%CONFIRM%"=="Y" exit /b

echo [1/4] Завершение всех процессов...
taskkill /F /IM "Antigravity.exe" 2>nul
taskkill /F /IM "antigravity" 2>nul
taskkill /F /IM "Antigravity IDE.exe" 2>nul
taskkill /F /IM "code.exe" 2>nul
taskkill /F /IM "language_server.exe" 2>nul
taskkill /F /IM "ag_dns.exe" 2>nul
timeout /t 2 /nobreak >nul

echo [2/4] Полная очистка кэша и хранилищ...
for %%P in ("Antigravity" "Antigravity IDE" "antigravity") do (
    if exist "%APPDATA%\%%~P\Cache" rmdir /S /Q "%APPDATA%\%%~P\Cache" 2>nul
    if exist "%APPDATA%\%%~P\Code Cache" rmdir /S /Q "%APPDATA%\%%~P\Code Cache" 2>nul
    if exist "%APPDATA%\%%~P\GPUCache" rmdir /S /Q "%APPDATA%\%%~P\GPUCache" 2>nul
    if exist "%APPDATA%\%%~P\IndexedDB" rmdir /S /Q "%APPDATA%\%%~P\IndexedDB" 2>nul
    if exist "%APPDATA%\%%~P\Session Storage" rmdir /S /Q "%APPDATA%\%%~P\Session Storage" 2>nul
    if exist "%LOCALAPPDATA%\%%~P\Cache" rmdir /S /Q "%LOCALAPPDATA%\%%~P\Cache" 2>nul
    if exist "%LOCALAPPDATA%\%%~P\GPUCache" rmdir /S /Q "%LOCALAPPDATA%\%%~P\GPUCache" 2>nul
    if exist "%LOCALAPPDATA%\%%~P\logs" rmdir /S /Q "%LOCALAPPDATA%\%%~P\logs" 2>nul
)

echo [3/4] Удаление битых файлов региональных токенов...
if exist "%USERPROFILE%\.gemini\antigravity\auth_cache.json" del /F /Q "%USERPROFILE%\.gemini\antigravity\auth_cache.json" 2>nul
if exist "%USERPROFILE%\.gemini\antigravity\session.json" del /F /Q "%USERPROFILE%\.gemini\antigravity\session.json" 2>nul
echo   [OK] Токены сессий удалены.

echo [4/4] Сброс системного кэша DNS...
ipconfig /flushdns >nul
powershell -NoProfile -Command "Clear-DnsClientCache" 2>nul
echo   [OK] DNS сброшен.

echo.
echo ======================================================================
echo Полный сброс завершен. Запустите Antigravity и выполните чистый вход.
echo ======================================================================
echo.
pause
