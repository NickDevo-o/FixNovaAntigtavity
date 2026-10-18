@echo off
chcp 65001 >nul
title Автоматическое добавление доменов в zapret
cls
echo ======================================================================
echo       ДОБАВЛЕНИЕ ДОМЕНОВ GOOGLE AI В СУЩЕСТВУЮЩИЙ ZAPRET
echo ======================================================================
echo.
echo Этот скрипт безопасно добавит необходимые домены Google AI и Antigravity
echo в ваш существующий файл list-general.txt, НЕ удаляя ваши домены
echo (Discord, YouTube и т.д.) и избегая дубликатов.
echo.

set SCRIPT_DIR=%~dp0
set LIST_SOURCE=%SCRIPT_DIR%..\lists\list-general.txt

if not exist "%LIST_SOURCE%" (
    echo [!] Ошибка: Не найден исходный файл: %LIST_SOURCE%
    pause
    exit /b
)

:ASK_PATH
echo Перетащите сюда папку с zapret (или укажите полный путь к папке zapret),
echo либо нажмите Enter, если zapret находится в папке Downloads:
set /p ZAPRET_DIR="Путь к папке zapret: "

if "%ZAPRET_DIR%"=="" (
    for /d %%D in ("%USERPROFILE%\Downloads\zapret*" "%USERPROFILE%\Downloads\telegram*\zapret*") do (
        if exist "%%D\lists\list-general.txt" (
            set "TARGET_FILE=%%D\lists\list-general.txt"
            goto FOUND
        )
    )
)

:: Убираем кавычки, если пользователь перетащил папку
set ZAPRET_DIR=%ZAPRET_DIR:"=%

if exist "%ZAPRET_DIR%\lists\list-general.txt" (
    set "TARGET_FILE=%ZAPRET_DIR%\lists\list-general.txt"
    goto FOUND
)
if exist "%ZAPRET_DIR%\list-general.txt" (
    set "TARGET_FILE=%ZAPRET_DIR%\list-general.txt"
    goto FOUND
)

echo [!] Файл list-general.txt не найден по указанному пути!
echo Пожалуйста, укажите верную папку (где есть папка lists\list-general.txt).
echo.
goto ASK_PATH

:FOUND
echo.
echo Найдена цель: %TARGET_FILE%
echo Создание резервной копии: %TARGET_FILE%.bak...
copy /y "%TARGET_FILE%" "%TARGET_FILE%.bak" >nul

echo Объединение доменов без дубликатов...
powershell -NoProfile -Command ^
    "$src = Get-Content -Path '%LIST_SOURCE%' -Encoding UTF8;" ^
    "$dst = Get-Content -Path '%TARGET_FILE%' -Encoding UTF8;" ^
    "$combined = ($dst + $src) | Where-Object { $_.Trim() -ne '' } | Select-Object -Unique;" ^
    "[System.IO.File]::WriteAllLines('%TARGET_FILE%', $combined, [System.Text.Encoding]::UTF8);"

echo.
echo ======================================================================
echo [УСПЕХ] Домены Google AI успешно добавлены в ваш list-general.txt!
echo.
echo ВАЖНО:
echo 1. Обязательно ПЕРЕЗАПУСТИТЕ zapret (service.bat или окно службы),
echo    так как zapret загружает список доменов ТОЛЬКО в момент запуска!
echo 2. После перезапуска проверьте чат в Antigravity.
echo ======================================================================
echo.
pause
