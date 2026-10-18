@echo off
chcp 65001 >nul
title NovaAntigravity Relay Launcher

echo =============================================================
echo   NovaAntigravity Relay - Open Source Unlocker
echo =============================================================
echo.

:: 1. Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден в системе!
    echo Установите Python 3.8+ с сайта python.org и поставьте галочку "Add to PATH".
    pause
    exit /b 1
)

:: 2. Check zapret (winws.exe)
tasklist /fi "imagename eq winws.exe" | findstr /i "winws.exe" >nul
if %errorlevel% neq 0 (
    echo [ВНИМАНИЕ] Процесс winws.exe (zapret) не запущен!
    echo Для прямого обхода блокировок РКН рекомендуется запустить zapret.
    echo Если вы используете собственный SOCKS5/VPN, можете продолжить.
    echo.
) else (
    echo [OK] zapret (winws.exe) активен.
)

:: 3. Kill any hanging relay on port 10809
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :10809 ^| findstr LISTENING') do (
    echo Освобождаю порт 10809 (PID %%a)...
    taskkill /f /pid %%a >nul 2>&1
)

:: 4. Start Relay in separate window
echo Запускаю локальный стриминг-прокси (relay.py)...
start "NovaAntigravity Relay" python "%~dp0relay.py" --port 10809

:: Give it a second to bind
timeout /t 2 /nobreak >nul

:: 5. Set environment variables for child processes
set AG_LS_PROXY=http://127.0.0.1:10809
set HTTP_PROXY=http://127.0.0.1:10809
set HTTPS_PROXY=http://127.0.0.1:10809

echo.
echo =============================================================
echo  [УСПЕХ] Прокси-релей запущен на 127.0.0.1:10809!
echo  Переменные окружения настроены:
echo    AG_LS_PROXY=http://127.0.0.1:10809
echo =============================================================
echo.

:: 6. Launch Antigravity
echo Выберите, что запустить:
echo  [1] Antigravity IDE (VS Code based)
echo  [2] Antigravity 2.0 (Standalone)
echo  [3] Оставить только релей в фоне
echo.
set /p choice="Ваш выбор [1/2/3]: "

if "%choice%"=="1" (
    if exist "%LOCALAPPDATA%\Programs\Antigravity IDE\Antigravity IDE.exe" (
        start "" "%LOCALAPPDATA%\Programs\Antigravity IDE\Antigravity IDE.exe"
    ) else (
        echo Не найден Antigravity IDE.exe в %%LOCALAPPDATA%%\Programs.
        pause
    )
) else if "%choice%"=="2" (
    if exist "%LOCALAPPDATA%\Programs\antigravity\Antigravity.exe" (
        start "" "%LOCALAPPDATA%\Programs\antigravity\Antigravity.exe"
    ) else (
        echo Не найден Antigravity.exe в %%LOCALAPPDATA%%\Programs.
        pause
    )
)

exit /b 0
