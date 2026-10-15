# One-time interactive setup for the SecurePrint agent - writes config.bat.
# Run by agent.bat the first time (or whenever config.bat is missing or
# still has the placeholder token). Deliberately in PowerShell rather than
# a cmd.exe `set /p` prompt: Read-Host uses Console.ReadLine() with none of
# `set /p`'s well-documented history of losing a second prompt's input to
# console-buffering quirks, and PowerShell is already a hard requirement
# for the agent itself, so this adds no new dependency.
[CmdletBinding()]
param()

Write-Host "SecurePrint Agent Setup"
Write-Host "========================"
Write-Host ""

$serverUrl = (Read-Host "SecurePrint server URL (e.g. https://print.example.com)").Trim()
if ([string]::IsNullOrWhiteSpace($serverUrl)) { $serverUrl = "https://print.example.com" }

Write-Host ""
Write-Host "Generate a Personal Access Token from the web app's Tokens page"
Write-Host "(sidebar -> Tokens -> Create Token), then paste it below."
$apiToken = (Read-Host "Personal Access Token").Trim()

if ([string]::IsNullOrWhiteSpace($apiToken)) {
    Write-Host ""
    Write-Host "No token entered - nothing was saved. Run this again when you have one."
    exit 1
}

$configPath = Join-Path $PSScriptRoot 'config.bat'
$lines = @(
    '@echo off'
    'REM Written by setup.ps1 - safe to hand-edit.'
    "set SERVER_URL=$serverUrl"
    "set API_TOKEN=$apiToken"
    'set POLL_SECONDS=20'
    'set RECONNECT_SECONDS=5'
    'set NOTIFY_ON_CONNECT=1'
    'REM Print capture - see config.example.bat. Needs setup-printer.ps1 first.'
    'set CAPTURE_ENABLED=0'
    'set SERVER_PRINTER='
    'set LOCAL_PRINTER='
    'set SUMATRA_PATH='
)
# ASCII: guaranteed no BOM, matches what cmd.exe expects for `set VAR=value`
# lines. Server URLs and PAT tokens (URL-safe base64) are pure ASCII, so
# nothing is lost.
Set-Content -Path $configPath -Value $lines -Encoding ASCII

Write-Host ""
Write-Host "Saved to config.bat."
exit 0
