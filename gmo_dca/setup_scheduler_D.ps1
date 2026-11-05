# GMO_DCA タスクを D: のコピーに向け直し、取りこぼし対策を有効化する。
# 管理者権限で実行すること。
$ErrorActionPreference = "Stop"

$py     = Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe"
$wd     = $PSScriptRoot
$script = Join-Path $wd "main.py"
$result = Join-Path $wd "_sched_result.txt"

try {
    # 1. 実行対象を D: に変更（python パス・引数・作業フォルダ）
    $action = New-ScheduledTaskAction -Execute $py -Argument ('"{0}"' -f $script) -WorkingDirectory $wd
    Set-ScheduledTask -TaskName "GMO_DCA" -Action $action | Out-Null

    # 2. 取りこぼし対策：寝ていても起床・後追い実行
    $task = Get-ScheduledTask -TaskName "GMO_DCA"
    $task.Settings.StartWhenAvailable = $true
    $task.Settings.WakeToRun          = $true
    Set-ScheduledTask -TaskName "GMO_DCA" -Settings $task.Settings | Out-Null

    "OK" | Out-File $result -Encoding utf8
} catch {
    ("FAIL: " + $_.Exception.Message) | Out-File $result -Encoding utf8
}
