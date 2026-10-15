# SecurePrint Windows Notification Agent - engine.
#
# Invoked by agent.bat. Authenticates with a Personal Access Token (never the
# account password), opens a live Server-Sent Events connection to the
# backend, and pops a tray notification the instant a print job is flagged
# CONFIDENTIAL/RESTRICTED, blocked, or fails closed. If the stream drops it
# automatically falls back to plain HTTP polling and keeps retrying the
# stream in the background - a flaky network degrades the agent's latency,
# never its reliability. Uses only what ships with Windows: no Python, no
# installer, no extra modules.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ServerUrl,
    [Parameter(Mandatory = $true)][string]$ApiToken,
    [int]$PollSeconds = 20,
    [int]$ReconnectSeconds = 5,
    [switch]$NotifyOnConnect,
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

$LogDir = Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir 'agent.log'

function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

# --------------------------------------------------------------------------
# Alert formatting - pure, no OS dependency. Never touches raw sensitive
# values: the API never sends them in the alert payload in the first place,
# so there's nothing here for the agent to leak even in its own log file.
# --------------------------------------------------------------------------

$BlockingEvents = @('BLOCKED', 'FAILED', 'REDACTION_VERIFICATION_FAILED')

function Format-Alert {
    param($Alert)

    $eventType = $Alert.event_type
    $filename = if ($Alert.filename) { $Alert.filename } else { 'a document' }
    $jobId = $Alert.job_id

    $topCategories = @()
    if ($Alert.categories) {
        $topCategories = $Alert.categories.PSObject.Properties | Sort-Object -Property Value -Descending | Select-Object -First 3
    }
    $categorySummary = ($topCategories | ForEach-Object { "$($_.Name) ($($_.Value))" }) -join ', '

    if ($eventType -eq 'AWAITING_DECISION') {
        $classification = if ($Alert.classification) { $Alert.classification } else { 'sensitive' }
        $title = "SecurePrint Alert: $classification"
        $message = if ($null -ne $Alert.risk_score) { "$filename - risk $($Alert.risk_score)/100" } else { $filename }
        if ($categorySummary) { $message += "`nDetected: $categorySummary" }
    } elseif ($BlockingEvents -contains $eventType) {
        $title = 'SecurePrint: Print Job Blocked'
        $reason = if ($Alert.message) { $Alert.message } else { 'blocked for security reasons' }
        $message = "$filename - $reason"
    } else {
        $title = 'SecurePrint Alert'
        $message = $filename
    }

    $url = if ($jobId) { "$ServerUrl/jobs/$jobId" } else { $ServerUrl }
    [PSCustomObject]@{ Title = $title; Message = $message; Url = $url }
}

# --------------------------------------------------------------------------
# Notification delivery. A NotifyIcon balloon tip is automatically rendered
# as a real Action Center toast by Windows 10/11 - no extra module, no app
# registration. Its tray presence and click handling both depend on the
# message loop being pumped regularly (Wait-WithPump / DoEvents calls
# throughout this script) - a plain synchronous script that just blocks on
# network I/O never does that on its own, which is why the icon can fail to
# appear (or a click silently do nothing) without it.
# --------------------------------------------------------------------------

function Wait-WithPump {
    # A NotifyIcon's tray presence is maintained through its hidden window's
    # message loop - a script that blocks for long stretches without ever
    # calling DoEvents() can leave the icon unregistered or let it vanish,
    # even though creating the NotifyIcon and setting Visible=$true threw no
    # error. This is used everywhere the script would otherwise sit idle so
    # the tray icon stays alive and responsive for the entire run, not just
    # briefly after showing a toast.
    param([int]$Seconds)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 150
    }
}

$script:BalloonUrl = $ServerUrl
$script:NotifyIcon = New-Object System.Windows.Forms.NotifyIcon
$script:NotifyIcon.Icon = [System.Drawing.SystemIcons]::Shield
$script:NotifyIcon.Text = 'SecurePrint Agent'
$script:NotifyIcon.add_BalloonTipClicked({
    if ($script:BalloonUrl) {
        try { Start-Process $script:BalloonUrl } catch { }
    }
})
$script:NotifyIcon.Visible = (-not $NoBalloon)
# Give the shell a moment to actually process the icon-add before doing
# anything else - without this, a script that immediately moves on to a
# long blocking network call can leave the add half-registered.
Wait-WithPump -Seconds 1

function Show-Toast {
    param([string]$Title, [string]$Message, [string]$Url)
    if ($NoBalloon) { return }
    $script:BalloonUrl = $Url
    $script:NotifyIcon.BalloonTipIcon = 'Warning'
    $script:NotifyIcon.BalloonTipTitle = $Title
    $script:NotifyIcon.BalloonTipText = $Message
    $script:NotifyIcon.ShowBalloonTip(8000)
    Wait-WithPump -Seconds 8
}

function Send-Alert {
    param($Alert)
    $formatted = Format-Alert -Alert $Alert
    Write-Log "ALERT $($Alert.event_type): $($formatted.Message -replace "`n", ' | ')"
    Show-Toast -Title $formatted.Title -Message $formatted.Message -Url $formatted.Url
}

# --------------------------------------------------------------------------
# Transport A: live push (SSE)
# --------------------------------------------------------------------------

function Get-LiveStream {
    param([datetime]$SinceUtc)
    $lastSeen = $SinceUtc
    $client = New-Object System.Net.Http.HttpClient
    try {
        $client.Timeout = [TimeSpan]::FromMinutes(10)
        $client.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue('Bearer', $ApiToken)
        $url = "$ServerUrl/api/v1/notifications/stream"
        $response = $client.GetAsync($url, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
        try {
            $response.EnsureSuccessStatusCode() | Out-Null
            $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
            $reader = New-Object System.IO.StreamReader($stream)
            try {
                $eventType = $null
                while ($script:Running -and -not $reader.EndOfStream) {
                    [System.Windows.Forms.Application]::DoEvents()
                    $line = $reader.ReadLine()
                    if ([string]::IsNullOrEmpty($line) -or $line.StartsWith(':')) { continue }
                    if ($line.StartsWith('event:')) {
                        $eventType = $line.Substring(6).Trim()
                        if ($eventType -eq 'connected') {
                            $script:Connected = $true
                            Write-Log 'Connected to SecurePrint live alert stream'
                        }
                    } elseif ($line.StartsWith('data:') -and $eventType -eq 'alert') {
                        $alert = ($line.Substring(5).Trim()) | ConvertFrom-Json
                        Send-Alert -Alert $alert
                        $lastSeen = [DateTime]::UtcNow
                    }
                }
            } finally {
                $reader.Dispose()
            }
        } finally {
            $response.Dispose()
        }
    } finally {
        $client.Dispose()
    }
    return $lastSeen
}

# --------------------------------------------------------------------------
# Transport B: fallback poll
# --------------------------------------------------------------------------

function ConvertTo-NaiveIso {
    # The backend stores and compares naive UTC timestamps (Python's
    # datetime.utcnow(), no offset). Sending an offset/'Z'-qualified string
    # here would make FastAPI parse `since` as timezone-aware, which then
    # fails to compare against the naive column - so every outgoing
    # timestamp is deliberately formatted with no timezone marker at all,
    # matching the server's own format exactly.
    param([datetime]$Value)
    $Value.ToString('yyyy-MM-ddTHH:mm:ss.ffffff', [Globalization.CultureInfo]::InvariantCulture)
}

function Invoke-Poll {
    param([datetime]$SinceUtc)
    try {
        $sinceParam = [Uri]::EscapeDataString((ConvertTo-NaiveIso $SinceUtc))
        $uri = "$ServerUrl/api/v1/notifications/recent?since=$sinceParam"
        $headers = @{ Authorization = "Bearer $ApiToken" }
        $resp = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get -TimeoutSec 15
        foreach ($alert in $resp.alerts) { Send-Alert -Alert $alert }
        # Invoke-RestMethod's JSON parser auto-coerces ISO-8601-looking string
        # values into [DateTime] objects. Use that object directly when it
        # already is one - forcing it through .ToString()/Parse() again would
        # round-trip via the current culture's default format and silently
        # drop the fractional seconds (verified empirically). Only parse it
        # ourselves if it came back as a plain string.
        if ($resp.server_time -is [DateTime]) {
            return $resp.server_time
        }
        return [DateTime]::Parse([string]$resp.server_time, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::None)
    } catch {
        Write-Log "Polling fallback failed ($($_.Exception.Message)) - will retry" 'WARN'
        return $SinceUtc
    }
}

# --------------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------------

$script:Running = $true
$script:Connected = $false

Write-Log "SecurePrint Agent starting - server: $ServerUrl"
if ($NotifyOnConnect) {
    Show-Toast -Title 'SecurePrint Agent' -Message 'Started - watching for security alerts.' -Url $ServerUrl
}

$lastSeen = [DateTime]::UtcNow
while ($script:Running) {
    try {
        $lastSeen = Get-LiveStream -SinceUtc $lastSeen
        $script:Connected = $false
    } catch {
        Write-Log "Event stream unavailable ($($_.Exception.Message)) - polling as a fallback" 'WARN'
        $script:Connected = $false
        $lastSeen = Invoke-Poll -SinceUtc $lastSeen
    }
    Wait-WithPump -Seconds $ReconnectSeconds
}
