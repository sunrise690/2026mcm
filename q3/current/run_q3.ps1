param(
    [Parameter(Mandatory=$true)]
    [string]$RobotId,
    [string]$BaseUrl = "http://127.0.0.1:2026"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Code = Join-Path $Root "workspace\code"
$Py = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
if (-not (Test-Path $Py)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $Py = $cmd.Source } else {
        $cmd = Get-Command py -ErrorAction SilentlyContinue
        if ($cmd) { $Py = $cmd.Source } else { throw "未找到 Python，请先安装 Python 3.11+。" }
    }
}
Set-Location $Code
Write-Host "Q3 code: $Code"
Write-Host "Python : $Py"
& $Py ".\live_q3.py" --robot-id $RobotId --base-url $BaseUrl
