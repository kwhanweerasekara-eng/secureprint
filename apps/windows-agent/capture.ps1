# SecurePrint print capture - the print interception and print control layers
# (proposal sections 3.3 and 3.6) on the Windows endpoint.
#
# Invoked by agent.bat when CAPTURE_ENABLED=1. Watches the file that the
# "SecurePrint" virtual printer (installed by setup-printer.ps1) renders each
# job to, and for every captured job:
#
#   1. moves the PDF out of the shared spool folder into this user's own
#      work folder, then uploads it to the SecurePrint API with the user's
#      Personal Access Token and deletes the local copy;
#   2. waits for the server's verdict;
#   3. for CONFIDENTIAL / RESTRICTED jobs, shows the security alert dialog
#      (Appendix C) - "Cancel printing" or "Mask and print";
#   4. releases ONLY the processed document returned by the server, either
#      through a printer managed by the server (SERVER_PRINTER) or to a local
#      Windows printer (LOCAL_PRINTER).
#
# It fails closed: if the server can't be reached, rejects the file, times
# out or blocks the job, nothing is printed and the user is told why.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ServerUrl,
    [Parameter(Mandatory = $true)][string]$ApiToken,
    [string]$PrinterName = 'SecurePrint',
    [string]$SpoolDir = (Join-Path $env:ProgramData 'SecurePrint\spool'),
    [string]$ServerPrinter = '',
    [string]$LocalPrinter = '',
    [string]$SumatraPath = '',
    [int]$VerdictTimeoutSeconds = 120,
    [switch]$NoBalloon
)

$ErrorActionPreference = 'Stop'
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
} catch {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Net.Http

$ServerUrl = $ServerUrl.TrimEnd('/')
$CaptureFile = Join-Path $SpoolDir 'capture.pdf'
$WorkDir = Join-Path $env:LOCALAPPDATA 'SecurePrint\work'
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

$LogDir = Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir 'capture.log'

function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

function Wait-WithPump {
    param([double]$Seconds)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 100
    }
}

# --------------------------------------------------------------------------
# Notifications and dialogs
# --------------------------------------------------------------------------

$script:NotifyIcon = New-Object System.Windows.Forms.NotifyIcon
$script:NotifyIcon.Icon = [System.Drawing.SystemIcons]::Shield
$script:NotifyIcon.Text = 'SecurePrint print capture'
$script:NotifyIcon.Visible = (-not $NoBalloon)
Wait-WithPump -Seconds 1

function Show-Toast {
    param([string]$Title, [string]$Message, [string]$Icon = 'Info')
    if ($NoBalloon) { return }
    $script:NotifyIcon.BalloonTipIcon = $Icon
    $script:NotifyIcon.BalloonTipTitle = $Title
    $script:NotifyIcon.BalloonTipText = $Message
    $script:NotifyIcon.ShowBalloonTip(6000)
}

function Show-Problem {
    # Used whenever a job is NOT printed, so the user always learns why.
    param([string]$Title, [string]$Message)
    Write-Log "$Title - $Message" 'WARN'
    [void][System.Windows.Forms.MessageBox]::Show(
        $Message, "SecurePrint - $Title",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Warning,
        [System.Windows.Forms.MessageBoxDefaultButton]::Button1,
        [System.Windows.Forms.MessageBoxOptions]::DefaultDesktopOnly)
}

$CategoryLabels = @{
    credential            = 'Password or credential'
    api_key               = 'API key or secret'
    card                  = 'Payment card number'
    bank_account          = 'Bank account number'
    iban                  = 'IBAN'
    nic                   = 'National identity number'
    passport              = 'Passport number'
    salary                = 'Salary value'
    employee_id           = 'Employee identifier'
    email                 = 'Email address'
    telephone             = 'Telephone number'
    classification_marker = 'Classification marker'
}

function Get-CategoryLabel {
    param([string]$Category)
    if ($CategoryLabels.ContainsKey($Category)) { return $CategoryLabels[$Category] }
    $words = $Category -split '_' | ForEach-Object { if ($_) { $_.Substring(0, 1).ToUpper() + $_.Substring(1) } }
    return ($words -join ' ')
}

function Show-SecurityAlert {
    # The dialog from Appendix C of the proposal. Shows the classification,
    # score and the CATEGORIES found - never the values themselves. Returns
    # 'Mask' or 'Cancel'; closing the window counts as Cancel.
    param($Job)

    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'SecurePrint - Document Security Alert'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.StartPosition = 'CenterScreen'
    $form.TopMost = $true
    $form.AutoSize = $true
    $form.AutoSizeMode = 'GrowAndShrink'
    $form.Padding = New-Object System.Windows.Forms.Padding(16)
    $form.Icon = [System.Drawing.SystemIcons]::Shield

    $panel = New-Object System.Windows.Forms.FlowLayoutPanel
    $panel.FlowDirection = 'TopDown'
    $panel.WrapContents = $false
    $panel.AutoSize = $true
    $form.Controls.Add($panel)

    function New-Label([string]$Text, [bool]$Bold = $false, [int]$TopMargin = 2) {
        $l = New-Object System.Windows.Forms.Label
        $l.Text = $Text
        $l.AutoSize = $true
        $l.MaximumSize = New-Object System.Drawing.Size(420, 0)
        $l.Margin = New-Object System.Windows.Forms.Padding(0, $TopMargin, 0, 2)
        $style = if ($Bold) { [System.Drawing.FontStyle]::Bold } else { [System.Drawing.FontStyle]::Regular }
        $l.Font = New-Object System.Drawing.Font('Segoe UI', 10, $style)
        return $l
    }

    $header = New-Label 'DOCUMENT SECURITY ALERT' $true 0
    $header.Font = New-Object System.Drawing.Font('Segoe UI', 13, [System.Drawing.FontStyle]::Bold)
    $header.ForeColor = if ($Job.classification -eq 'RESTRICTED') { [System.Drawing.Color]::Firebrick } else { [System.Drawing.Color]::DarkOrange }
    $panel.Controls.Add($header)
    $panel.Controls.Add((New-Label 'Sensitive information was detected in this document.' $false 8))
    $panel.Controls.Add((New-Label "Document:  $($Job.original_filename)" $false 10))
    $panel.Controls.Add((New-Label "Risk score:  $($Job.risk_score) of 100"))
    $panel.Controls.Add((New-Label "Classification:  $($Job.classification)" $true))
    $panel.Controls.Add((New-Label 'Categories detected' $true 10))
    foreach ($d in ($Job.detections | Sort-Object -Property count -Descending)) {
        $plural = if ($d.count -eq 1) { 'occurrence' } else { 'occurrences' }
        $panel.Controls.Add((New-Label ("    {0}  -  {1} {2}" -f (Get-CategoryLabel $d.category), $d.count, $plural)))
    }
    $panel.Controls.Add((New-Label 'If you continue, the values listed above will be masked and a classification footer will be applied to every page before printing.' $false 10))

    $buttons = New-Object System.Windows.Forms.FlowLayoutPanel
    $buttons.FlowDirection = 'LeftToRight'
    $buttons.AutoSize = $true
    $buttons.Margin = New-Object System.Windows.Forms.Padding(0, 14, 0, 0)

    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Text = 'Cancel printing'
    $cancel.AutoSize = $true
    $cancel.Padding = New-Object System.Windows.Forms.Padding(8, 4, 8, 4)
    $cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel

    $mask = New-Object System.Windows.Forms.Button
    $mask.Text = 'Mask and print'
    $mask.AutoSize = $true
    $mask.Padding = New-Object System.Windows.Forms.Padding(8, 4, 8, 4)
    $mask.DialogResult = [System.Windows.Forms.DialogResult]::OK

    $buttons.Controls.Add($cancel)
    $buttons.Controls.Add($mask)
    $panel.Controls.Add($buttons)

    # No AcceptButton on purpose: pressing Enter must not print by reflex.
    # Esc and the close box both cancel.
    $form.CancelButton = $cancel
    $form.Add_Shown({ $form.Activate(); $cancel.Focus() })

    # Keep collecting new print jobs while the user reads the alert, so a
    # second job printed meanwhile can't be overwritten in the spool file.
    $timer = New-Object System.Windows.Forms.Timer
    $timer.Interval = 500
    $timer.Add_Tick({ Receive-Capture })
    $timer.Start()
    try {
        $result = $form.ShowDialog()
    } finally {
        $timer.Stop()
        $timer.Dispose()
        $form.Dispose()
    }
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) { return 'Mask' }
    return 'Cancel'
}

# --------------------------------------------------------------------------
# Capture: the spooler renders each job to $CaptureFile
# --------------------------------------------------------------------------

$script:Queue = New-Object System.Collections.Queue
$script:PendingDocName = $null
$script:LastSeenSize = -1

function Update-PendingDocName {
    # Windows only exposes the application's document name ("payroll.xlsx")
    # while the job is still in the spooler, so remember it for the file
    # that is about to land.
    try {
        $spooled = Get-PrintJob -PrinterName $PrinterName -ErrorAction Stop | Select-Object -First 1
        if ($spooled -and $spooled.DocumentName) { $script:PendingDocName = $spooled.DocumentName }
        return [bool]$spooled
    } catch {
        return $false
    }
}

function ConvertTo-PdfName {
    param([string]$Name)
    if ([string]::IsNullOrWhiteSpace($Name)) { $Name = 'Print job ' + (Get-Date -Format 'yyyy-MM-dd HHmmss') }
    $Name = ($Name -replace '^Microsoft (Word|Excel|PowerPoint) - ', '')
    foreach ($c in [IO.Path]::GetInvalidFileNameChars()) { $Name = $Name.Replace([string]$c, '_') }
    $Name = [IO.Path]::GetFileNameWithoutExtension($Name)
    if ($Name.Length -gt 120) { $Name = $Name.Substring(0, 120) }
    return "$Name.pdf"
}

function Test-CaptureReady {
    if (-not (Test-Path -LiteralPath $CaptureFile)) { $script:LastSeenSize = -1; return $false }
    if (Update-PendingDocName) { return $false }  # still spooling
    try {
        $stream = [IO.File]::Open($CaptureFile, 'Open', 'ReadWrite', 'None')
        $size = $stream.Length
        $stream.Close()
    } catch {
        return $false  # the spooler still has it open
    }
    # Require the same non-zero size on two consecutive checks.
    if ($size -le 0 -or $size -ne $script:LastSeenSize) { $script:LastSeenSize = $size; return $false }
    $script:LastSeenSize = -1
    return $true
}

function Receive-Capture {
    [void](Update-PendingDocName)
    if (-not (Test-CaptureReady)) { return }
    $target = Join-Path $WorkDir ([guid]::NewGuid().ToString() + '.pdf')
    try {
        Move-Item -LiteralPath $CaptureFile -Destination $target -Force
    } catch {
        Write-Log "Could not take the captured job from the spool folder: $($_.Exception.Message)" 'WARN'
        return
    }
    $item = [PSCustomObject]@{ Path = $target; Name = (ConvertTo-PdfName $script:PendingDocName) }
    $script:PendingDocName = $null
    $script:Queue.Enqueue($item)
    Write-Log "Captured print job '$($item.Name)'"
}

# --------------------------------------------------------------------------
# SecurePrint API
# --------------------------------------------------------------------------

function Invoke-Api {
    param([string]$Method, [string]$Path, $Body = $null)
    $params = @{
        Uri        = "$ServerUrl$Path"
        Method     = $Method
        Headers    = @{ Authorization = "Bearer $ApiToken" }
        TimeoutSec = 90
    }
    if ($null -ne $Body) {
        $params.Body = ($Body | ConvertTo-Json -Compress)
        $params.ContentType = 'application/json'
    }
    Invoke-RestMethod @params
}

function Get-ApiError {
    param($ErrorRecord)
    $detail = $ErrorRecord.ErrorDetails.Message
    if ($detail) {
        try { return ($detail | ConvertFrom-Json).detail } catch { return $detail }
    }
    return $ErrorRecord.Exception.Message
}

function Send-Capture {
    param($Item)
    $client = New-Object System.Net.Http.HttpClient
    try {
        $client.Timeout = [TimeSpan]::FromSeconds(120)
        $client.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue('Bearer', $ApiToken)
        $content = New-Object System.Net.Http.MultipartFormDataContent
        $file = [System.Net.Http.ByteArrayContent]::new([IO.File]::ReadAllBytes($Item.Path))
        $file.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse('application/pdf')
        $content.Add($file, 'file', $Item.Name)
        $response = $client.PostAsync("$ServerUrl/api/v1/documents/analyze?source=virtual_printer", $content).GetAwaiter().GetResult()
        $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            $reason = $body
            try { $reason = ($body | ConvertFrom-Json).detail } catch { }
            throw "the server refused it ($([int]$response.StatusCode)): $reason"
        }
        return ($body | ConvertFrom-Json)
    } finally {
        $client.Dispose()
    }
}

function Wait-JobSettled {
    param([string]$JobId, [string[]]$Statuses)
    $deadline = (Get-Date).AddSeconds($VerdictTimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $job = Invoke-Api -Method Get -Path "/api/v1/jobs/$JobId"
        if ($Statuses -contains $job.status) { return $job }
        Receive-Capture
        Wait-WithPump -Seconds 0.4
    }
    return $null
}

# --------------------------------------------------------------------------
# Release (print control layer) - only ever the server's processed PDF
# --------------------------------------------------------------------------

$script:TempFiles = New-Object System.Collections.ArrayList

function Send-ToLocalPrinter {
    param([string]$PdfPath)
    if ($SumatraPath -and (Test-Path -LiteralPath $SumatraPath)) {
        Start-Process -FilePath $SumatraPath -ArgumentList @('-print-to', "`"$LocalPrinter`"", '-silent', "`"$PdfPath`"") -WindowStyle Hidden -Wait
    } else {
        # Needs a PDF reader that registers the PrintTo verb (Adobe Acrobat
        # Reader, Foxit, SumatraPDF). Microsoft Edge does not.
        Start-Process -FilePath $PdfPath -Verb PrintTo -ArgumentList "`"$LocalPrinter`"" -WindowStyle Hidden
    }
}

function Publish-Job {
    param($Job)
    $name = $Job.original_filename
    if ($PrinterId) {
        try {
            [void](Invoke-Api -Method Post -Path "/api/v1/jobs/$($Job.id)/print" -Body @{ printer_id = $PrinterId })
        } catch {
            Show-Problem 'Not printed' "'$name' was checked and is ready, but the server could not deliver it to the printer: $(Get-ApiError $_)`n`nYou can retry from the job page in the SecurePrint web app."
            return
        }
        Write-Log "Released $($Job.id) to managed printer $PrinterId"
        Show-Toast 'SecurePrint' "'$name' ($($Job.classification)) was sent to the printer."
        return
    }

    if ($LocalPrinter) {
        $out = Join-Path $WorkDir "$($Job.id)-release.pdf"
        try {
            Invoke-WebRequest -Uri "$ServerUrl/api/v1/jobs/$($Job.id)/document?download=1" -Headers @{ Authorization = "Bearer $ApiToken" } -OutFile $out -UseBasicParsing -TimeoutSec 90
            Send-ToLocalPrinter -PdfPath $out
            [void](Invoke-Api -Method Post -Path "/api/v1/jobs/$($Job.id)/print" -Body @{})
        } catch {
            Show-Problem 'Not printed' "'$name' was checked and is ready, but it could not be sent to '$LocalPrinter': $($_.Exception.Message)"
            return
        } finally {
            [void]$script:TempFiles.Add([PSCustomObject]@{ Path = $out; DeleteAfter = (Get-Date).AddMinutes(2) })
        }
        Write-Log "Released $($Job.id) to local printer '$LocalPrinter'"
        Show-Toast 'SecurePrint' "'$name' ($($Job.classification)) was sent to $LocalPrinter."
        return
    }

    Show-Problem 'No printer set' "'$name' was checked and is ready, but no release printer is configured on this PC. Set SERVER_PRINTER or LOCAL_PRINTER in config.bat, or print it from the job page in the SecurePrint web app."
}

function Remove-ExpiredTempFiles {
    # The PDF reader may still be reading the file just after PrintTo returns,
    # so released copies are kept briefly and then deleted.
    foreach ($t in @($script:TempFiles)) {
        if ((Get-Date) -ge $t.DeleteAfter) {
            Remove-Item -LiteralPath $t.Path -Force -ErrorAction SilentlyContinue
            if (-not (Test-Path -LiteralPath $t.Path)) { $script:TempFiles.Remove($t) }
        }
    }
}

# --------------------------------------------------------------------------
# One captured job, start to finish
# --------------------------------------------------------------------------

function Invoke-CapturedJob {
    param($Item)

    try {
        $created = Send-Capture -Item $Item
    } catch {
        $ex = $_.Exception
        while ($ex.InnerException) { $ex = $ex.InnerException }
        Show-Problem 'Not printed' "'$($Item.Name)' could not be checked by SecurePrint, so it was not printed: $($ex.Message)"
        return
    } finally {
        # The captured file holds the unmasked document - never keep it.
        Remove-Item -LiteralPath $Item.Path -Force -ErrorAction SilentlyContinue
    }
    Write-Log "Submitted '$($Item.Name)' as $($created.id)"

    try {
        $job = Wait-JobSettled -JobId $created.id -Statuses @('AWAITING_DECISION', 'READY', 'BLOCKED', 'FAILED', 'CANCELLED')
        if (-not $job) {
            Show-Problem 'Not printed' "SecurePrint did not finish checking '$($Item.Name)' in time, so it was not printed."
            return
        }

        if ($job.status -eq 'AWAITING_DECISION') {
            $choice = Show-SecurityAlert -Job $job
            Write-Log "User chose '$choice' for $($job.id) ($($job.classification), score $($job.risk_score))"
            if ($choice -ne 'Mask') {
                [void](Invoke-Api -Method Post -Path "/api/v1/jobs/$($job.id)/cancel")
                Show-Toast 'SecurePrint' "Printing of '$($job.original_filename)' was cancelled."
                return
            }
            [void](Invoke-Api -Method Post -Path "/api/v1/jobs/$($job.id)/sanitize")
            $job = Wait-JobSettled -JobId $job.id -Statuses @('READY', 'BLOCKED', 'FAILED')
            if (-not $job) {
                Show-Problem 'Not printed' "SecurePrint did not finish masking '$($Item.Name)' in time, so it was not printed."
                return
            }
        }

        if ($job.status -eq 'READY') {
            Publish-Job -Job $job
        } elseif ($job.status -ne 'CANCELLED') {
            $reason = if ($job.status_message) { $job.status_message } else { "The job ended as $($job.status)." }
            Show-Problem 'Print job blocked' "'$($job.original_filename)' was not printed.`n`n$reason"
        }
    } catch {
        Show-Problem 'Not printed' "Something went wrong while handling '$($Item.Name)', so it was not printed: $(Get-ApiError $_)"
    }
}

# --------------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------------

if ($LocalPrinter -and ($LocalPrinter -eq $PrinterName)) {
    Write-Log "LOCAL_PRINTER cannot be the SecurePrint printer itself - jobs would loop forever." 'ERROR'
    exit 1
}
if (-not (Get-Printer -Name $PrinterName -ErrorAction SilentlyContinue)) {
    Write-Log "Printer '$PrinterName' is not installed. Run setup-printer.ps1 as Administrator first." 'ERROR'
    Show-Problem 'Setup needed' "The '$PrinterName' printer is not installed on this PC. Ask an administrator to run setup-printer.ps1."
    exit 1
}
# SERVER_PRINTER may be the printer's name as shown on the web app's Printers
# page, or its id.
$PrinterId = ''
if ($ServerPrinter) {
    try {
        $match = @(Invoke-Api -Method Get -Path '/api/v1/printers') | Where-Object { $_.id -eq $ServerPrinter -or $_.name -eq $ServerPrinter } | Select-Object -First 1
    } catch {
        $match = $null
        Write-Log "Could not load the printer list from the server: $(Get-ApiError $_)" 'WARN'
    }
    if ($match) {
        $PrinterId = $match.id
        Write-Log "Releasing checked jobs to server printer '$($match.name)'"
    } else {
        Write-Log "Server printer '$ServerPrinter' was not found on the Printers page." 'ERROR'
        Show-Problem 'Setup needed' "The printer '$ServerPrinter' set in config.bat was not found in SecurePrint. Check the name on the web app's Printers page."
        exit 1
    }
}
if (-not $PrinterId -and -not $LocalPrinter) {
    Write-Log 'No release printer configured (SERVER_PRINTER or LOCAL_PRINTER) - checked jobs will be held for the web app.' 'WARN'
}

Write-Log "SecurePrint print capture started - watching $CaptureFile"
while ($true) {
    try {
        Receive-Capture
        if ($script:Queue.Count -gt 0) {
            Invoke-CapturedJob -Item ($script:Queue.Dequeue())
        }
        Remove-ExpiredTempFiles
    } catch {
        Write-Log "Capture loop error: $($_.Exception.Message)" 'ERROR'
    }
    Wait-WithPump -Seconds 0.5
}
