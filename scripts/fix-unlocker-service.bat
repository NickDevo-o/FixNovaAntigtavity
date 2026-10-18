@echo off
chcp 65001 >nul
title Antigravity Unlocker - Перезапуск службы обхода
cls
echo ======================================================================
echo           СБРОС И ВОССТАНОВЛЕНИЕ СЛУЖБЫ ОБХОДА (AG_DNS)
echo ======================================================================
echo.
echo Этот скрипт нужен, если в Unlocker пишет:
echo "Служба обхода не работает... Жму починить, и все равно ошибка возвращается".
echo.

:: Проверка прав администратора
net session >nul 2>&1
if not "%ERRORLEVEL%"=="0" (
    echo [!] ВНИМАНИЕ: Скрипт запущен БЕЗ прав Администратора!
    echo Кликните по файлу правой кнопкой мыши и выберите:
    echo "Запуск от имени администратора".
    echo.
    pause
    exit /b
)

echo [1/3] Принудительное завершение зависшего ag_dns...
powershell -NoProfile -Command "Stop-Process -Name ag_dns -Force -ErrorAction SilentlyContinue"
taskkill /F /IM "ag_dns.exe" 2>nul
echo   [OK] Процессы ag_dns остановлены.

echo [2/3] Очистка кэша DNS клиентов Windows...
ipconfig /flushdns >nul
powershell -NoProfile -Command "Clear-DnsClientCache" 2>nul
echo   [OK] DNS-кэш сброшен.

echo [3/3] Освобождение сокетов и сетевых служб...
powershell -NoProfile -Command "Get-Process -Name language_server -ErrorAction SilentlyContinue | Stop-Process -Force"
echo   [OK] Фоновые сокеты освобождены.

echo.
echo ======================================================================
echo Сброс успешно выполнен!
echo.
echo Теперь:
echo 1. Откройте Antigravity Unlocker 2 (от имени Администратора).
echo 2. Нажмите кнопку "Починить" / "Запустить службу" в Unlocker.
echo 3. Теперь служба запустится без ошибок!
echo ======================================================================
echo.
pause
