# 清原達郎式スクリーナー 週次ランチャ
# 親ディレクトリ（試用）を作業ディレクトリにして名前空間パッケージ「株」を解決する。
$ErrorActionPreference = "Stop"
$python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe"

# $PSScriptRoot = ...\試用\株\stock_screener  →  2つ上が ...\試用
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $root

Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 清原式スクリーナー開始: $root"
& $python -m 株.stock_screener.main
$code = $LASTEXITCODE
Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] 終了コード: $code"
exit $code
