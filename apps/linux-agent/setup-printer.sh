#!/usr/bin/env bash
# Installs the "SecurePrint" virtual printer on Ubuntu (run once, with sudo).
#
# The printer uses the cups-pdf backend: every job printed to it is written as
# a PDF into ~/.secureprint/spool of the user who printed it, where capture.py
# (running in that user's session) picks it up. Nothing reaches paper until
# SecurePrint has checked the document.
#
#   sudo ./setup-printer.sh            install
#   sudo ./setup-printer.sh --uninstall
set -euo pipefail

PRINTER=SecurePrint
CONF=/etc/cups/cups-pdf.conf

if [[ $EUID -ne 0 ]]; then
    echo "Run this with sudo." >&2
    exit 1
fi

if [[ "${1:-}" == "--uninstall" ]]; then
    lpadmin -x "$PRINTER" 2>/dev/null && echo "Removed printer $PRINTER." || echo "Printer $PRINTER was not installed."
    exit 0
fi

if ! dpkg -s printer-driver-cups-pdf >/dev/null 2>&1; then
    apt-get update
    apt-get install -y printer-driver-cups-pdf
fi

# Each user's jobs go to their own spool folder, named job_<n>-<title>.pdf so
# capture.py can show the document's title in the alert.
cp -n "$CONF" "$CONF.secureprint-backup" 2>/dev/null || true
set_option() {
    if grep -qE "^[#[:space:]]*$1[[:space:]]" "$CONF"; then
        sed -i -E "s|^[#[:space:]]*$1[[:space:]].*|$1 $2|" "$CONF"
    else
        echo "$1 $2" >> "$CONF"
    fi
}
set_option Out '${HOME}/.secureprint/spool'
set_option Label 1
set_option AnonDirName /var/spool/cups-pdf/ANONYMOUS

MODEL=$(lpinfo -m | awk '/CUPS-PDF/ {print $1; exit}')
if [[ -z "$MODEL" ]]; then
    echo "Could not find the CUPS-PDF driver (lpinfo -m). Is printer-driver-cups-pdf installed?" >&2
    exit 1
fi

lpadmin -p "$PRINTER" -E -v cups-pdf:/ -m "$MODEL" \
    -D "SecurePrint (checked before printing)" -L "SecurePrint DLP" -o printer-is-shared=false
systemctl restart cups 2>/dev/null || service cups restart

echo "Installed printer $PRINTER (driver $MODEL)."
echo "Each user now runs capture.py in their desktop session - see README.md."
