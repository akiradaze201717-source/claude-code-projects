@echo off
chcp 65001 >nul

set TASK_NAME=GMO_BTC_Screener
set SCRIPT_DIR=%~dp0

for /f "delims=" %%i in ('where python 2^>nul') do (
    set PYTHON_PATH=%%i
    goto :found_python
)
echo [ERROR] Python が見つかりません。
pause
exit /b 1
:found_python

echo タスク名: %TASK_NAME%
echo Python:   %PYTHON_PATH%
echo スクリプト: %SCRIPT_DIR%main.py
echo 実行時刻: 毎日 22:00
echo.

schtasks /Query /TN "%TASK_NAME%" >nul 2>&1
if %errorlevel% equ 0 (
    echo 既存タスクを更新します...
    schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1
)

schtasks /Create /TN "%TASK_NAME%" /TR "\"%PYTHON_PATH%\" \"%SCRIPT_DIR%main.py\"" /SC DAILY /ST 22:00 /F /RU "%USERNAME%"

if %errorlevel% equ 0 (
    echo.
    echo [OK] タスクスケジューラに登録しました。毎日 22:00 に実行されます。
    echo 手動実行: schtasks /Run /TN "%TASK_NAME%"
    echo 確認:     Win+R → taskschd.msc
) else (
    echo.
    echo [FAIL] 管理者権限で再実行してください。
    echo 右クリック → 管理者として実行
)

echo.
pause
