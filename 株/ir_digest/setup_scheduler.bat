@echo off
chcp 65001 >nul
echo ============================================
echo  IR資料まとめ・乖離ランキングBot
echo  Windowsタスクスケジューラ設定
echo ============================================
echo.

set SCRIPT_DIR=%~dp0

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: python が見つかりません。Pythonをインストールしてください。
    pause
    exit /b 1
)

set TASK_NAME=IrDigestDaily

echo タスク名: %TASK_NAME%
echo 実行時刻: 毎日 18:00（決算開示が出そろう夕方）
echo スクリプト: %SCRIPT_DIR%main.py
echo.

schtasks /query /tn "%TASK_NAME%" >nul 2>&1
if %errorlevel% equ 0 (
    echo 既存タスクを更新します...
    schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
)

schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "python \"%SCRIPT_DIR%main.py\"" ^
    /sc daily ^
    /st 18:00 ^
    /f

if %errorlevel% equ 0 (
    echo.
    echo タスクスケジューラに登録しました！
    echo 毎日 18:00 にIRまとめが自動実行・メール送信されます。
    echo 確認: Win+R → taskschd.msc で「%TASK_NAME%」を確認
) else (
    echo.
    echo ERROR: タスクの登録に失敗しました。管理者権限で再実行してください。
)

echo.
pause
