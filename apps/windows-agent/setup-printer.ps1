# Installs (or removes) the "SecurePrint" virtual printer - the print
# interception layer described in section 3.3 of the project proposal.
#
# The printer uses the built-in "Microsoft Print To PDF" driver with a local
# port that points at a file. When a user prints to it, Windows renders the
# job to a PDF at that path without a Save As dialog, and capture.ps1 picks
# the file up, sends it to the SecurePrint API for analysis, and only the
# processed result is ever released to a physical printer. Nothing has to be
# downloaded: both the driver and the cmdlets ship with Windows 10/11.
#
# Must be run from an elevated (Administrator) PowerShell:
#   powershell -ExecutionPolicy Bypass -File setup-printer.ps1
#   powershell -ExecutionPolicy Bypass -File setup-printer.ps1 -Uninstall
[CmdletBinding()]
param(
    [string]$PrinterName = 'SecurePrint',
    [string]$SpoolDir = (Join-Path $env:ProgramData 'SecurePrint\spool'),
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$DriverName = 'Microsoft Print To PDF'
$PortName = Join-Path $SpoolDir 'capture.pdf'

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host '[ERROR] Adding a printer needs Administrator rights.'
    Write-Host 'Right-click PowerShell, choose "Run as administrator", and run this script again.'
    exit 1
}

if ($Uninstall) {
    if (Get-Printer -Name $PrinterName -ErrorAction SilentlyContinue) {
        Remove-Printer -Name $PrinterName
        Write-Host "Removed printer '$PrinterName'."
    }
    if (Get-PrinterPort -Name $PortName -ErrorAction SilentlyContinue) {
        Remove-PrinterPort -Name $PortName
        Write-Host "Removed port '$PortName'."
    }
    exit 0
}

if (-not (Get-PrinterDriver -Name $DriverName -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] The '$DriverName' driver is not installed."
    Write-Host 'Turn it on in "Turn Windows features on or off" (Microsoft Print to PDF), then run this again.'
    exit 1
}

# The spooler writes captured jobs here and the agent (running as the signed-in
# user) needs to move and delete them, so ordinary users get Modify rights on
# this one folder only.
New-Item -ItemType Directory -Force -Path $SpoolDir | Out-Null
$acl = Get-Acl $SpoolDir
$usersSid = New-Object Security.Principal.SecurityIdentifier('S-1-5-32-545')
$rule = New-Object Security.AccessControl.FileSystemAccessRule($usersSid, 'Modify', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
$acl.AddAccessRule($rule)
Set-Acl -Path $SpoolDir -AclObject $acl

if (-not (Get-PrinterPort -Name $PortName -ErrorAction SilentlyContinue)) {
    Add-PrinterPort -Name $PortName
    Write-Host "Created local port '$PortName'."
}

$existing = Get-Printer -Name $PrinterName -ErrorAction SilentlyContinue
if ($existing) {
    Set-Printer -Name $PrinterName -DriverName $DriverName -PortName $PortName
    Write-Host "Updated existing printer '$PrinterName'."
} else {
    Add-Printer -Name $PrinterName -DriverName $DriverName -PortName $PortName
    Write-Host "Installed printer '$PrinterName'."
}

Write-Host ''
Write-Host "Done. Print jobs sent to '$PrinterName' are written to:"
Write-Host "  $PortName"
Write-Host 'and picked up by the SecurePrint agent (set CAPTURE_ENABLED=1 in config.bat).'
Write-Host ''
Write-Host 'Tip: to make SecurePrint the only route to paper, set it as the default'
Write-Host 'printer and remove or restrict direct access to the physical printers.'
exit 0
