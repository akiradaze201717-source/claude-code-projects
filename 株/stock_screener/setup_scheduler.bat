@echo off
chcp 65001 >nul
echo ============================================
echo  清原達郎式 株スクリーニングBot
echo  Windowsタスクスケジューラ設定
echo ============================================
echo.

REM スクリプトのディレクトリを取得
set SCRIPT_DIR=%~dp0

REM Pythonのパスを確認
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: python が見つかりません。Pythonをインストールしてください。
    pause
    exit /b 1
)

REM タスク名
set TASK_NAME=KiyoharaStockScreener

echo タスク名: %TASK_NAME%
echo 実行時刻: 毎日 16:30
echo スクリプト: %SCRIPT_DIR%main.py
echo.

REM 既存タスクの削除（存在する場合）
schtasks /query /tn "%TASK_NAME%" >nul 2>&1
if %errorlevel% equ 0 (
    echo 既存タスクを更新します...
    schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
)

REM タスク作成
schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "python \"%SCRIPT_DIR%main.py\"" ^
    /sc daily ^
    /st 16:30 ^
    /f

if %errorlevel% equ 0 (
    echo.
    echo タスクスケジューラに登録しました！
    echo 毎日 16:30 にスクリーニングが自動実行されます。
    echo.
    echo 確認: タスクスケジューラを開いて「%TASK_NAME%」を確認してください。
    echo   Win+R → taskschd.msc
) else (
    echo.
    echo ERROR: タスクの登録に失敗しました。
    echo 管理者権限で再実行してください。
)

echo.
pause
