# AssetMgmt_WeeklyRemind タスクを登録する（毎週月曜07:00）。管理者権限で実行すること。
$ErrorActionPreference = "Stop"

$taskName = "AssetMgmt_WeeklyRemind"
$wd       = $PSScriptRoot
$ps1      = Join-Path $wd "run_remind.ps1"
$result   = Join-Path $wd "_sched_result_remind.txt"

try {
    $action  = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $ps1) -WorkingDirectory $wd
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 7:00am
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun

    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Settings $settings -Force | Out-Null

    "OK" | Out-File $result -Encoding utf8
} catch {
    ("FAIL: " + $_.Exception.Message) | Out-File $result -Encoding utf8
}
