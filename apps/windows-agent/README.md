# SecurePrint Windows Notification Agent

Runs on a staff or admin's Windows machine, watches their SecurePrint print
jobs in real time, and pops a notification the moment sensitive data is
identified — `AWAITING_DECISION` (CONFIDENTIAL/RESTRICTED), `BLOCKED`,
`FAILED`, or a failed redaction verification. Admins see every user's alerts;
staff see their own.

It can also **capture print jobs** (optional, see below): a "SecurePrint"
virtual printer catches what users print, the server checks it, the user
gets the security alert on their desktop, and only the processed copy is
sent to a real printer.

**No Python, no installer, nothing to download.** The agent is a `.bat` file
plus a PowerShell script it launches — both ship with every supported
version of Windows already. Copy this folder anywhere and run it.

## How it connects

```
SecurePrint API --(SSE: GET /api/v1/notifications/stream)--> agent.ps1 --> tray notification
                  (falls back to polling GET /api/v1/notifications/recent
                   if the stream drops, and keeps retrying the stream)
```

Authentication is a **Personal Access Token**, not the account password —
generate one from the web app's **Tokens** page (sidebar → Tokens → Create
Token). The token is shown once; paste it into `config.bat` and it's never
needed again in that form. Revoking a token from the web app immediately
stops that agent from receiving alerts.

## Running it

Double-click **`agent.bat`**.

- **First run**: it has no `config.bat` yet, so it runs a short interactive
  setup right there in the same window — it asks for your SecurePrint
  server URL and a Personal Access Token (from the Tokens page), then saves
  `config.bat` and connects immediately, no separate file to edit and no
  second run needed.
- **Every run after that**: it connects immediately. A tray icon appears,
  and notifications pop up automatically as alerts arrive. Close the window
  or press `Ctrl+C` to stop.

If you'd rather set it up by hand, copy `config.example.bat` to `config.bat`
and edit the values yourself — `agent.bat` skips the prompt whenever a valid
`config.bat` already exists.

Logs are written to `logs\agent.log` next to the script (useful for
checking what the agent has seen without relying on notifications you may
have missed).

## Print capture (the SecurePrint virtual printer)

This is the print interception layer from the project proposal (section 3.3).
Users print from Word, Excel or a browser exactly as usual, choosing the
**SecurePrint** printer.

```
App --print--> "SecurePrint" printer (Microsoft Print to PDF -> file port)
          --> capture.ps1 picks up the PDF, uploads it with the token
          --> API: extract -> detect -> score -> classify
          --> CONFIDENTIAL/RESTRICTED: desktop alert [Cancel printing] [Mask and print]
          --> processed PDF only --> server printer (IPP/socket) or local printer
```

**One-time setup on each PC (as Administrator):**

```
powershell -ExecutionPolicy Bypass -File setup-printer.ps1
```

This adds a printer named `SecurePrint` that uses the built-in *Microsoft
Print to PDF* driver and writes each job to
`C:\ProgramData\SecurePrint\spool\capture.pdf`. Nothing is downloaded.
Remove it again with `setup-printer.ps1 -Uninstall`.

**Then in `config.bat`:**

| Setting | Meaning |
|---|---|
| `CAPTURE_ENABLED=1` | Start the capture loop with the agent. |
| `SERVER_PRINTER=Lab Printer` | Name of a printer on the web app's Printers page. The server sends the processed PDF straight to it. Recommended. |
| `LOCAL_PRINTER=HP LaserJet` | Or: a Windows printer on this PC. The agent downloads the processed PDF and prints it. Needs a PDF reader with "print to" support (Adobe Reader), or set `SUMATRA_PATH` to SumatraPDF.exe for silent printing. |

What happens to each job:

- **PUBLIC / INTERNAL**: printed straight away with the classification footer; a small notification confirms it.
- **CONFIDENTIAL / RESTRICTED**: the *Document Security Alert* dialog shows the classification, the risk score and the categories found (never the values). *Cancel printing* cancels the job and records it in the audit log; closing the dialog or pressing Esc also cancels. *Mask and print* masks the values, adds the footer (and watermark for RESTRICTED) and prints.
- **Scanned / image-only, blocked, or any error** (server unreachable, timeout): nothing is printed and a message says why. The capture fails closed.

The captured PDF holds the unmasked document, so it is moved out of the shared
spool folder into the user's own `%LOCALAPPDATA%\SecurePrint\work` folder
and deleted as soon as it has been uploaded. Capture runs as its own
background process, logs to `logs\capture.log`, and keeps running after the
agent window is closed (end `powershell.exe` in Task Manager to stop it).

Known limits of the prototype: the original physical printers are still
visible to users unless an administrator removes or restricts them, and two
jobs printed within the same second can overwrite each other in the spool
file (the second is then simply not printed).

## Running automatically at logon

Press `Win+R`, type `shell:startup`, and drop a shortcut in that folder
pointing at **`run-hidden.vbs`** (not `agent.bat` directly) — this starts
the agent with no console window on screen; the tray icon and notifications
work exactly the same either way.

## Files

| File | Purpose |
|---|---|
| `agent.bat` | Entry point. Runs setup on first use, then launches the engine. |
| `agent.ps1` | The engine: SSE stream, polling fallback, alert formatting, notifications. You shouldn't need to edit this. |
| `setup.ps1` | One-time interactive prompt for server URL + token; writes `config.bat`. |
| `config.example.bat` | Template for setting up `config.bat` by hand instead. |
| `config.bat` | Your server URL and token. Created on first run; not tracked in git. |
| `setup-printer.ps1` | One-time, as Administrator: installs or removes the `SecurePrint` virtual printer. |
| `capture.ps1` | Print capture: picks up jobs from the virtual printer, sends them for checking, shows the security alert and releases the processed PDF. |
| `run-hidden.vbs` | Optional - launches `agent.bat` with no visible window, for startup shortcuts. |

## What a notification looks like

- **Sensitive data identified**: *"SecurePrint Alert: RESTRICTED — payroll_august.pdf, risk 100/100. Detected: nic (1), bank_account (2), salary (5)"*
- **Blocked**: *"SecurePrint: Print Job Blocked — scan.pdf, Scan / image-only document detected. OCR is required."*

Clicking a notification within a few seconds of it appearing opens that
job's detail page in the browser. No raw sensitive values are ever included
— the API never sends them in the alert payload in the first place, so
there's nothing for the agent to leak even in its own log file.

## Requirements

Windows 10 or 11 (or Windows Server 2016+) with Windows PowerShell 5.1,
which is on every install by default. Nothing else to install.
