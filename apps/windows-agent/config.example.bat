@echo off
REM SecurePrint Agent configuration.
REM
REM You normally won't need this file: agent.bat runs an interactive setup
REM (setup.ps1) the first time and writes config.bat for you. This template
REM is only for setting it up by hand instead - copy it to config.bat and
REM edit the values below.

REM Your SecurePrint server address - no trailing slash.
set SERVER_URL=https://print.example.com

REM Personal Access Token, generated from the web app's Tokens page
REM (sidebar -> Tokens -> Create Token). It is shown once - paste it here.
set API_TOKEN=PASTE_YOUR_TOKEN_HERE

REM How often to poll for alerts if the live connection drops, in seconds.
set POLL_SECONDS=20

REM How long to wait before retrying the live connection after it drops, in seconds.
set RECONNECT_SECONDS=5

REM Show a "Started" notification when the agent connects (1 = yes, 0 = no).
set NOTIFY_ON_CONNECT=1

REM --- Print capture (the "SecurePrint" virtual printer) ---------------------
REM Turn on after an administrator has run setup-printer.ps1 on this PC.
REM Jobs printed to "SecurePrint" are checked by the server before printing.
set CAPTURE_ENABLED=0

REM Where checked documents are released. Set ONE of these:
REM   SERVER_PRINTER - name of a printer on the web app's Printers page; the
REM                    server sends the processed PDF to it directly (recommended).
REM   LOCAL_PRINTER  - name of a Windows printer on this PC, e.g. "HP LaserJet".
set SERVER_PRINTER=
set LOCAL_PRINTER=

REM Optional, for LOCAL_PRINTER: full path to SumatraPDF.exe for silent printing.
REM Without it, a PDF reader that supports "print to" (e.g. Adobe Reader) is used.
set SUMATRA_PATH=
