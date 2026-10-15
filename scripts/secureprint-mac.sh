#!/bin/bash
# Start, stop and check SecurePrint on a Mac.
#
#   scripts/secureprint-mac.sh start     API (8000), web app (3000), print capture
#   scripts/secureprint-mac.sh stop      stop all three
#   scripts/secureprint-mac.sh restart   stop, then start
#   scripts/secureprint-mac.sh status    what is running
#   scripts/secureprint-mac.sh logs      follow the API, web and capture logs
#
# The API and web app run in the background; their output goes to
# ~/.secureprint/api.log and ~/.secureprint/web.log. Print capture is the
# launchd agent installed by apps/linux-agent/setup-printer-mac.sh.
# While capture is stopped, nothing printed to SecurePrint is released:
# jobs wait in the macOS print queue (fail closed).
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$HOME/.secureprint"
LABEL=lk.secureprint.capture
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
mkdir -p "$LOGS"

pids_on() { lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null; }

wait_for() { # port, name
    for _ in $(seq 1 60); do
        if pids_on "$1" >/dev/null; then echo "  $2 is up on http://localhost:$1"; return 0; fi
        sleep 1
    done
    echo "  $2 did not start - see $LOGS/$3" >&2
    return 1
}

stop_port() { # port, name, pid file
    local pids pidfile="$LOGS/$3"
    # The process this script started (npm for the web app), then whatever
    # still holds the port (the server itself, or one started another way).
    if [[ -f "$pidfile" ]]; then kill -TERM "$(cat "$pidfile")" 2>/dev/null; rm -f "$pidfile"; fi
    pids="$(pids_on "$1")"
    if [[ -n "$pids" ]]; then
        kill -TERM $pids 2>/dev/null
        for _ in $(seq 1 10); do pids_on "$1" >/dev/null || break; sleep 0.5; done
        pids="$(pids_on "$1")"
        [[ -n "$pids" ]] && kill -KILL $pids 2>/dev/null
    fi
    echo "  $2 stopped"
}

start_api() {
    if pids_on 8000 >/dev/null; then echo "  API already running on port 8000"; return; fi
    if [[ ! -x "$ROOT/.venv/bin/uvicorn" ]]; then
        echo "  .venv is missing - run: python3.12 -m venv .venv && ./.venv/bin/pip install -r apps/api/requirements.txt" >&2
        return 1
    fi
    (cd "$ROOT" && ./.venv/bin/python -m alembic -c apps/api/alembic.ini upgrade head >>"$LOGS/api.log" 2>&1)
    cd "$ROOT" && nohup ./.venv/bin/uvicorn apps.api.main:app --app-dir . --port 8000 </dev/null >>"$LOGS/api.log" 2>&1 &
    echo $! >"$LOGS/api.pid"
    wait_for 8000 "API" api.log
}

start_web() {
    if pids_on 3000 >/dev/null; then echo "  Web app already running on port 3000"; return; fi
    if [[ ! -d "$ROOT/apps/web/node_modules" ]]; then
        echo "  Installing web app packages (first run only)..."
        (cd "$ROOT/apps/web" && npm ci >>"$LOGS/web.log" 2>&1)
    fi
    cd "$ROOT/apps/web" && nohup npm run dev </dev/null >>"$LOGS/web.log" 2>&1 &
    echo $! >"$LOGS/web.pid"
    wait_for 3000 "Web app" web.log
}

start_capture() {
    if [[ ! -f "$PLIST" ]]; then
        echo "  Print capture is not installed - run: cd apps/linux-agent && PYTHON=python3.12 bash setup-printer-mac.sh"
        return
    fi
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
        launchctl kickstart -k "$DOMAIN/$LABEL"
    else
        launchctl bootstrap "$DOMAIN" "$PLIST"
    fi
    for _ in $(seq 1 20); do nc -z localhost 8001 2>/dev/null && break; sleep 0.5; done
    if nc -z localhost 8001 2>/dev/null; then echo "  Print capture is up (printer receiver on port 8001)"
    else echo "  Print capture did not start - see $LOGS/capture.log and $LOGS/launchd.log" >&2; fi
}

stop_capture() {
    if launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null; then echo "  Print capture stopped"
    else echo "  Print capture was not running"; fi
}

status() {
    if pids_on 8000 >/dev/null; then echo "  API          running   http://localhost:8000/docs"; else echo "  API          stopped"; fi
    if pids_on 3000 >/dev/null; then echo "  Web app      running   http://localhost:3000"; else echo "  Web app      stopped"; fi
    if nc -z localhost 8001 2>/dev/null; then echo "  Capture      running   (printer receiver on 8001)"; else echo "  Capture      stopped"; fi
    if lpstat -p SecurePrint >/dev/null 2>&1; then
        echo "  Printer      $(lpstat -p SecurePrint | head -1)"
        # e.g. "Waiting for the SecurePrint server" while jobs are held
        local message; message="$(lpstat -p SecurePrint | sed -n '2p' | sed 's/^[[:space:]]*//')"
        [[ -n "$message" ]] && echo "               $message"
        local queued; queued="$(lpstat -o SecurePrint 2>/dev/null | wc -l | tr -d ' ')"
        echo "  Print queue  $queued job(s) waiting"
    else
        echo "  Printer      not installed"
    fi
}

case "${1:-}" in
    start)   echo "Starting SecurePrint"; start_api; start_web; start_capture ;;
    stop)    echo "Stopping SecurePrint"; stop_capture; stop_port 3000 "Web app" web.pid; stop_port 8000 "API" api.pid ;;
    restart) "$0" stop; "$0" start ;;
    status)  echo "SecurePrint status"; status ;;
    logs)    tail -n 20 -F "$LOGS/api.log" "$LOGS/web.log" "$LOGS/capture.log" ;;
    *)       sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
