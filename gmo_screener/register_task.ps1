$python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe"
$script = Join-Path $PSScriptRoot "main.py"

$action   = New-ScheduledTaskAction -Execute $python -Argument "`"$script`""
$trigger  = New-ScheduledTaskTrigger -Daily -At "22:00"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask -TaskName "GMO_BTC_Screener" -Action $action -Trigger $trigger -Settings $settings -Force

Write-Host "登録完了。毎日 22:00 に実行されます。"
