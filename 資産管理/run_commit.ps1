# 週次コミット実行ラッパー。タスクスケジューラから呼び出される。
$ErrorActionPreference = "Stop"
$py = Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe"
$wd = $PSScriptRoot

Set-Location $wd
& $py "main.py" "commit"
