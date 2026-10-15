@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ===========================================
echo   SecurePrint Notification Agent
echo ===========================================
echo.

where powershell >nul 2>nul
if errorlevel 1 (
    echo [ERROR] PowerShell was not found on this machine. This agent requires
    echo Windows PowerShell, which ships with every supported version of Windows.
    pause
    exit /b 1
)

set "NEED_SETUP=0"
if not exist "config.bat" set "NEED_SETUP=1"
if "!NEED_SETUP!"=="1" goto :do_setup

call config.bat
if "!SERVER_URL!"=="" goto :do_setup
if "!API_TOKEN!"=="" goto :do_setup
if "!API_TOKEN!"=="PASTE_YOUR_TOKEN_HERE" goto :do_setup
goto :setup_done

:do_setup
echo [SETUP] Let's connect this agent to your SecurePrint server.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if not exist "config.bat" (
    echo.
    echo [ERROR] Setup did not finish, so config.bat was not created.
    echo Run this file again when you're ready.
    pause
    exit /b 1
)
call config.bat
if "!API_TOKEN!"=="" goto :no_token
if "!API_TOKEN!"=="PASTE_YOUR_TOKEN_HERE" goto :no_token
echo.
goto :setup_done

:no_token
echo.
echo [ERROR] config.bat exists but has no API_TOKEN set. Delete config.bat
echo and run this file again, or edit it by hand and paste in a token from
echo the SecurePrint web app's Tokens page.
pause
exit /b 1

:setup_done
if "!POLL_SECONDS!"=="" set "POLL_SECONDS=20"
if "!RECONNECT_SECONDS!"=="" set "RECONNECT_SECONDS=5"

set "EXTRA_ARGS="
if not "!NOTIFY_ON_CONNECT!"=="0" set "EXTRA_ARGS=-NotifyOnConnect"

if "!CAPTURE_ENABLED!"=="1" (
    set "CAPTURE_ARGS="
    if not "!SERVER_PRINTER!"=="" set "CAPTURE_ARGS=!CAPTURE_ARGS! -ServerPrinter "!SERVER_PRINTER!""
    if not "!LOCAL_PRINTER!"=="" set "CAPTURE_ARGS=!CAPTURE_ARGS! -LocalPrinter "!LOCAL_PRINTER!""
    if not "!SUMATRA_PATH!"=="" set "CAPTURE_ARGS=!CAPTURE_ARGS! -SumatraPath "!SUMATRA_PATH!""
    echo Print capture: ON - jobs sent to the SecurePrint printer are checked before printing.
    start "SecurePrint print capture" /min powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0capture.ps1" -ServerUrl "!SERVER_URL!" -ApiToken "!API_TOKEN!" !CAPTURE_ARGS!
) else (
    echo Print capture: OFF - set CAPTURE_ENABLED=1 in config.bat to turn it on.
)

echo Server: !SERVER_URL!
echo Token:  !API_TOKEN:~0,12!...
echo.
echo Watching for security alerts. A tray icon will appear; notifications pop
echo up automatically the moment sensitive data is identified. Close this
echo window or press Ctrl+C to stop.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0agent.ps1" -ServerUrl "!SERVER_URL!" -ApiToken "!API_TOKEN!" -PollSeconds !POLL_SECONDS! -ReconnectSeconds !RECONNECT_SECONDS! !EXTRA_ARGS!

echo.
echo Agent stopped.
pause
