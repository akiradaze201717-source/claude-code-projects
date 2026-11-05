@echo off
REM ASCII-only launcher. Delegates to the PowerShell script so the
REM Japanese path / module name are handled with correct Unicode encoding.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_screener.ps1"
