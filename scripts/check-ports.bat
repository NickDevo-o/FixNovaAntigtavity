@echo off
chcp 65001 >nul
title Antigravity Fix - Diagnostic Utility
cls
echo ======================================================================
echo          ДИАГНОСТИКА СВЯЗКИ ANTIGRAVITY + UNLOCKER + ZAPRET
echo ======================================================================
echo.

set FAILURES=0

:: 1. Проверка запущенных процессов
echo [1/5] Проверка запущенных процессов...
tasklist /FI "IMAGENAME eq winws.exe" 2>NUL | find /I /N "winws.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo   [OK] zapret (winws.exe) активен.
) else (
    echo   [!] ВНИМАНИЕ: zapret (winws.exe) НЕ найден в процессах!
    echo       Запустите zapret через service.bat или preset.bat от имени Администратора.
    set /a FAILURES+=1
)

tasklist /FI "IMAGENAME eq Antigravity*" 2>NUL | find /I "Antigravity">NUL
if "%ERRORLEVEL%"=="0" (
    echo   [OK] Antigravity процесс обнаружен.
) else (
    echo   [i] Antigravity сейчас не запущен (это нормально перед настройкой).
)
echo.

:: 2. Проверка порта 10809
echo [2/5] Проверка локального порта 10809 (HTTP-прокси)...
netstat -ano | findstr /R /C:":10809 .*LISTENING" >nul
if "%ERRORLEVEL%"=="0" (
    echo   [OK] Порт 10809 прослушивается (сервер/прокси запущен).
) else (
    echo   [!] ВНИМАНИЕ: Порт 10809 НЕ прослушивается!
    echo       Убедитесь, что Antigravity Unlocker 2 запущен и настроен на этот порт,
    echo       либо встроенный выход Unlocker активен.
    set /a FAILURES+=1
)
echo.

:: 3. Проверка активных VPN адаптеров
echo [3/5] Проверка посторонних VPN / TUN адаптеров...
ipconfig | findstr /I "WireGuard TAP-Windows Wintun Cloudflare" >nul
if "%ERRORLEVEL%"=="0" (
    echo   [!] ВНИМАНИЕ: Обнаружен активный VPN-адаптер (WireGuard / TAP / TUN / WARP)!
    echo       Инструкция требует ПОЛНОСТЬЮ ОТКЛЮЧИТЬ VPN, иначе WinDivert и Unlocker
    echo       будут конфликтовать или слать трафик по неверным маршрутам.
    set /a FAILURES+=1
) else (
    echo   [OK] Активных VPN адаптеров не обнаружено.
)
echo.

:: 4. Проверка разрешения DNS
echo [4/5] Тест DNS-резолвинга ключевых доменов Google AI...
powershell -NoProfile -Command ^
    "try { $ip = [System.Net.Dns]::GetHostAddresses('generativelanguage.googleapis.com'); Write-Host '  [OK] generativelanguage.googleapis.com -> ' $ip[0].IPAddressToString } catch { Write-Host '  [!] Ошибка разрешения DNS: generativelanguage.googleapis.com' -ForegroundColor Red }"

powershell -NoProfile -Command ^
    "try { $ip = [System.Net.Dns]::GetHostAddresses('alkalicore-pa.clients6.google.com'); Write-Host '  [OK] alkalicore-pa.clients6.google.com -> ' $ip[0].IPAddressToString } catch { Write-Host '  [!] Ошибка разрешения DNS: alkalicore-pa.clients6.google.com' -ForegroundColor Red }"
echo.

:: 5. Тест соединения через локальный прокси
echo [5/5] Тестирование доступности прокси 127.0.0.1:10809...
powershell -NoProfile -Command ^
    "try { $tcp = New-Object System.Net.Sockets.TcpClient('127.0.0.1', 10809); $tcp.Close(); Write-Host '  [OK] TCP-соединение с 127.0.0.1:10809 успешно установлено.' } catch { Write-Host '  [!] Не удалось подключиться по TCP к 127.0.0.1:10809. ' $_.Exception.Message -ForegroundColor Yellow }"
echo.

echo ======================================================================
if %FAILURES% gtr 0 (
    echo ОБНАРУЖЕНЫ ПРЕДУПРЕЖДЕНИЯ (%FAILURES%). Сверьтесь с TROUBLESHOOTING.md!
) else (
    echo ВСЕ БАЗОВЫЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО!
)
echo ======================================================================
echo.
pause
