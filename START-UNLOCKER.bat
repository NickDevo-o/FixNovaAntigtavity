@echo off
chcp 65001 >nul
title Antigravity Unlocker Next - Панель управления
cd /d "%~dp0"

:MENU
cls
echo ======================================================================
echo       🚀 ANTIGRAVITY UNLOCKER NEXT (NOVA GATEWAY & RELAY)
echo   Открытый обход блокировок без VPN: zapret + DoH + Anti-128K Pacing
echo ======================================================================
echo.

:: Быстрая проверка zapret
tasklist /fi "imagename eq winws.exe" 2>nul | findstr /i "winws.exe" >nul
if %errorlevel% equ 0 (
    echo   [🟢 zapret] Активен (winws.exe запущен)
) else (
    echo   [🟡 zapret] НЕ обнаружен (рекомендуется запустить zapret service.bat)
)

:: Быстрая проверка статуса патча
python relay\patcher.py --status 2>nul | findstr /i "PATCHED" >nul
if %errorlevel% equ 0 (
    echo   [🟢 Патч IDE] Применен (Onboarding и Pro-тир разблокированы)
) else (
    echo   [⚪ Патч IDE] Оригинал (не пропатчен)
)

echo.
echo ======================================================================
echo   ВЫБЕРИТЕ ДЕЙСТВИЕ:
echo ======================================================================
echo   [G] 🖥️  Открыть графическую панель (Antigravity Unlocker GUI)
echo   [1] ⚡ ЗАПУСК В 1 КЛИК (Релей + Проверка патча + Запуск IDE)
echo   [2] 🔧 Пропатчить Antigravity IDE (Обход ошибки 400 и Pro-тир)
echo   [3] ↩️  Восстановить оригинал Antigravity IDE (Откат из бэкапа)
echo   [4] 🧹 Очистить кэш (Устранение черного экрана и сброс токенов)
echo   [5] 🩺 Экспресс-диагностика (Проверка портов, VPN, zapret)
echo   [6] ➕ Добавить домены Google AI в zapret (add-to-zapret)
echo   [0] Выход
echo ======================================================================
echo.
set /p ACTION="Введите номер действия [G, 1-6, 0]: "

if /i "%ACTION%"=="0" exit /b
if /i "%ACTION%"=="g" (
    start "" "%~dp0START-GUI.bat"
    exit /b 0
)
if "%ACTION%"=="1" goto QUICK_START
if "%ACTION%"=="2" goto DO_PATCH
if "%ACTION%"=="3" goto DO_RESTORE
if "%ACTION%"=="4" goto DO_CLEAN
if "%ACTION%"=="5" goto DO_DIAGNOSTICS
if "%ACTION%"=="6" goto DO_ADD_ZAPRET

echo Неверный ввод!
timeout /t 2 >nul
goto MENU

:QUICK_START
cls
echo ======================================================================
echo                ЗАПУСК ANTIGRAVITY UNLOCKER NEXT
echo ======================================================================
echo.

:: 1. Проверка Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python 3 не найден в PATH!
    echo Установите Python с python.org или через winget install Python.Python.3.13
    pause
    goto MENU
)

:: 2. Автопроверка и применение патча IDE
python relay\patcher.py --status 2>nul | findstr /i "PATCHED" >nul
if %errorlevel% neq 0 (
    echo [i] Применяем безопасный патч для обхода онбординга...
    python relay\patcher.py --patch
) else (
    echo [OK] Antigravity IDE уже пропатчена.
)

:: 3. Очистка зависшего порта 10809
echo [i] Проверка доступности порта 10809...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr :10809 ^| findstr LISTENING') do (
    taskkill /f /pid %%a >nul 2>&1
)
taskkill /f /im "ag_dns.exe" >nul 2>&1

:: 4. Запуск открытого Relay (с DoH и защитой от 128КБ)
echo [i] Запуск стриминг-шлюза (DoH 1.1.1.1 + Anti-Overflow)...
start "Antigravity Relay" python "%~dp0relay\relay.py" --port 10809
timeout /t 2 /nobreak >nul

:: 5. Настройка окружения
set AG_LS_PROXY=http://127.0.0.1:10809
set HTTP_PROXY=http://127.0.0.1:10809
set HTTPS_PROXY=http://127.0.0.1:10809

echo.
echo ======================================================================
echo  [УСПЕХ] Шлюз активен на http://127.0.0.1:10809!
echo ======================================================================
echo.

:: 6. Выбор клиента для запуска
if exist "%LOCALAPPDATA%\Programs\Antigravity IDE\Antigravity IDE.exe" (
    echo Запуск Antigravity IDE...
    start "" "%LOCALAPPDATA%\Programs\Antigravity IDE\Antigravity IDE.exe"
) else if exist "%LOCALAPPDATA%\Programs\antigravity\Antigravity.exe" (
    echo Запуск Antigravity 2.0...
    start "" "%LOCALAPPDATA%\Programs\antigravity\Antigravity.exe"
) else (
    echo [!] Исполняемый файл Antigravity не найден в стандартных путях.
    echo Шлюз запущен на порту 10809 — вы можете открыть клиент вручную.
    pause
)

exit /b 0

:DO_PATCH
cls
python relay\patcher.py --patch
pause
goto MENU

:DO_RESTORE
cls
python relay\patcher.py --restore
pause
goto MENU

:DO_CLEAN
cls
call scripts\clear-antigravity-cache.bat
goto MENU

:DO_DIAGNOSTICS
cls
call scripts\check-ports.bat
pause
goto MENU

:DO_ADD_ZAPRET
cls
call scripts\add-to-zapret.bat
pause
goto MENU
