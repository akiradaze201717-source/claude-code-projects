@echo off
REM Repoint GMO_DCA scheduled task to the D: drive copy (self-elevating)
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator privileges. Please click "Yes" on the UAC prompt...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)
echo Running as administrator...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_scheduler_D.ps1"
echo.
type "%~dp0_sched_result.txt"
echo.
echo Done. You can close this window.
pause
