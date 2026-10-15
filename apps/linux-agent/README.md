# SecurePrint print capture for Ubuntu and macOS

The Ubuntu counterpart of `apps/windows-agent` (proposal Table 4.2, secondary
target). The user prints to the **SecurePrint** printer from any application.
The job is checked by the SecurePrint server before anything is printed:

1. The SecurePrint printer (cups-pdf) saves the job as a PDF in `~/.secureprint/spool`.
2. `capture.py` uploads it with the user's access token (`source=virtual_printer`).
3. PUBLIC and INTERNAL jobs are released straight away. CONFIDENTIAL and
   RESTRICTED jobs show the security alert (Appendix C). The user can choose
   **Mask and print** or **Cancel printing**. Closing the window or pressing Esc cancels.
4. Only the processed PDF (masked, footer, watermark) is printed, on a
   server printer (`SERVER_PRINTER`) or a local CUPS printer (`LOCAL_PRINTER`, via `lp`).

The tool fails closed. If the server rejects the file, takes too long or
blocks the job, nothing is printed and the user is told why. The captured,
unmasked PDF is deleted as soon as it has been uploaded, and until then it sits
in a spool folder only this user can read.

While the server can't be reached, or rejects the access token, jobs wait
instead of being dropped. On macOS the SecurePrint printer tells CUPS it is not
accepting jobs, so they stay in the computer's own print queue with the message
"Waiting for the SecurePrint server", and are checked as soon as it is back.
The user gets a notification when this starts and when it ends.

## Install on Ubuntu

Tested on Ubuntu 22.04 and 24.04. It needs Python 3 with Tkinter.

```bash
sudo apt install python3-tk
sudo ./setup-printer.sh                      # adds the SecurePrint printer

mkdir -p ~/.config/secureprint ~/.local/share/secureprint
cp agent.conf.example ~/.config/secureprint/agent.conf
nano ~/.config/secureprint/agent.conf        # SERVER_URL, API_TOKEN, a release printer
cp capture.py ~/.local/share/secureprint/

# start it at every login
mkdir -p ~/.config/systemd/user
cp secureprint-capture.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now secureprint-capture
```

Log: `~/.secureprint/capture.log`.

## Try it

```bash
lp -d SecurePrint some-payslip.pdf
```

This should bring up the security alert. You can also print from LibreOffice or Firefox and pick
**SecurePrint** as the printer.

To test without a desktop (for example in CI), set the config values as
environment variables and run:

```bash
python3 capture.py --once --decide mask      # or --decide cancel
```

## Install on macOS

macOS has CUPS built in but no PDF-to-folder printer, so `capture.py` also
runs a small printer receiver on `localhost:8001` (`ipp_receiver.py`). The
SecurePrint printer is an IPP printer pointing at it, and macOS sends every
job to it as a PDF.

1. Install Python 3.12 from python.org (the Xcode Python 3.9 is too old for the server), then start the server from the project folder: `python3.12 -m venv .venv && ./.venv/bin/pip install -r apps/api/requirements.txt` once, then `make api-dev`.
2. Sign in to the web app and create an access token (Settings > Access tokens).
3. In Terminal:

   ```bash
   cd apps/linux-agent
   bash setup-printer-mac.sh    # first run creates ~/.config/secureprint/agent.conf - paste the token there
   bash setup-printer-mac.sh    # second run starts the capture and (re)creates the printer
   ```

4. Print anything to **SecurePrint Protected Printer**.

The copies, two-sided and colour settings from the Print dialog are kept and
passed on to the real printer, and the computer account that printed the job
is recorded in the audit log. If you update `capture.py` or `ipp_receiver.py`,
run `setup-printer-mac.sh` again: it copies the new files and recreates the
printer so macOS reads its current capabilities.

With no real printer attached, checked documents are saved to
`~/Desktop/SecurePrint Released` and opened in Preview (`RELEASE_DIR`). Set
`LOCAL_PRINTER` to a real printer's queue name (`lpstat -p`) to print on paper.
The capture starts at every login (`~/Library/LaunchAgents/lk.secureprint.capture.plist`).
Its log is in `~/.secureprint/capture.log`.

The security alert uses Tkinter. If `python3 -c "import tkinter"` fails, install
Python from python.org or run `brew install python-tk`.

Remove: `bash setup-printer-mac.sh --uninstall`. To use a specific Python, run `PYTHON=python3.12 bash setup-printer-mac.sh`.

## Remove (Ubuntu)

```bash
systemctl --user disable --now secureprint-capture
sudo ./setup-printer.sh --uninstall
```
