#!/bin/bash
# Sets up SecurePrint print capture on macOS for the current user.
#
#   ./setup-printer-mac.sh              install (asks for your Mac password once, for lpadmin)
#   ./setup-printer-mac.sh --uninstall
#
# macOS has no PDF-to-folder printer backend, so the "SecurePrint" printer is
# an IPP printer at ipp://localhost:8001/ipp/print, served by capture.py
# itself (ipp_receiver.py). CUPS converts every job to PDF and hands it to
# capture.py, which checks it with the SecurePrint server before release.
set -euo pipefail

PRINTER=SecurePrint
PORT=8001
HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/Library/Application Support/SecurePrint"
CONF_DIR="$HOME/.config/secureprint"
LABEL=lk.secureprint.capture
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [[ "${1:-}" == "--uninstall" ]]; then
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    sudo lpadmin -x "$PRINTER" 2>/dev/null || true
    echo "Removed the $PRINTER printer and the capture service. Settings in $CONF_DIR were kept."
    exit 0
fi

# launchd needs an absolute path. PYTHON=python3.12 picks a specific version.
PYTHON="$(command -v "${PYTHON:-python3}" || true)"
if [[ -z "$PYTHON" ]]; then
    echo "Python not found. Install Python 3.12 from python.org." >&2
    exit 1
fi
if ! "$PYTHON" -c "import tkinter; tkinter.Tcl()" 2>/dev/null; then
    echo "$PYTHON has no working Tkinter (needed for the security alert)." >&2
    echo "Install Python from python.org, or: brew install python-tk" >&2
    exit 1
fi

mkdir -p "$APP" "$CONF_DIR" "$HOME/Library/LaunchAgents"
cp "$HERE/capture.py" "$HERE/ipp_receiver.py" "$APP/"
if [[ ! -f "$CONF_DIR/agent.conf" ]]; then
    cp "$HERE/agent.conf.example" "$CONF_DIR/agent.conf"
    sed -i '' -e "s|^IPP_PORT=.*|IPP_PORT=$PORT|" \
              -e "s|^RELEASE_DIR=.*|RELEASE_DIR=~/Desktop/SecurePrint Released|" \
              -e "s|^SERVER_URL=.*|SERVER_URL=http://localhost:8000|" "$CONF_DIR/agent.conf"
    echo "Created $CONF_DIR/agent.conf - add your access token (API_TOKEN) there, then run this script again."
    open -e "$CONF_DIR/agent.conf" 2>/dev/null || true
    exit 0
fi
if ! grep -qE '^API_TOKEN=.+' "$CONF_DIR/agent.conf"; then
    echo "Set API_TOKEN in $CONF_DIR/agent.conf first (web app: Settings > Access tokens)." >&2
    exit 1
fi

# Start capture.py at every login (and now).
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array><string>$PYTHON</string><string>$APP/capture.py</string></array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>LimitLoadToSessionType</key><string>Aqua</string>
    <key>StandardErrorPath</key><string>$HOME/.secureprint/launchd.log</string>
</dict>
</plist>
PLIST
mkdir -p "$HOME/.secureprint"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

for _ in $(seq 1 20); do
    nc -z localhost "$PORT" 2>/dev/null && break
    sleep 0.5
done
if ! nc -z localhost "$PORT" 2>/dev/null; then
    echo "capture.py did not start - see ~/.secureprint/capture.log and ~/.secureprint/launchd.log" >&2
    exit 1
fi

# (Re)create the printer while the receiver is running, so macOS can read its
# capabilities and send every job as PDF ("IPP Everywhere").
sudo lpadmin -x "$PRINTER" 2>/dev/null || true
sudo lpadmin -p "$PRINTER" -E -v "ipp://localhost:$PORT/ipp/print" -m everywhere \
    -D "SecurePrint Protected Printer" -L "Checked before printing" -o printer-is-shared=false
echo "Done. Print anything to \"SecurePrint Protected Printer\" to try it."
