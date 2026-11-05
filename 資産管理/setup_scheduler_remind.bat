@echo off
chcp 65001 >nul
REM AssetMgmt_WeeklyRemind タスクを登録する（自己昇格）
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo 管理者権限へ昇格します。UACが出たら「はい」を押してください...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)
echo 管理者として実行中...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_scheduler_remind.ps1"
echo.
type "%~dp0_sched_result_remind.txt"
echo.
echo 完了しました。このウィンドウは閉じて構いません。
pause
