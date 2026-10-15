# Stopping and restarting SecurePrint on the Mac

SecurePrint on your Mac is four separate pieces. Each one starts and stops on its own.

| Piece | What it does | Address | How it runs |
|---|---|---|---|
| API server | Checks, scores and masks documents | http://localhost:8000 | A Terminal window (`make api-dev`) |
| Website | The dashboard you sign in to | http://localhost:3000 | A Terminal window (`make web-dev`) |
| Print capture | Receives print jobs and shows the security alert | localhost:8001 | In the background, started by macOS at every login |
| SecurePrint Protected Printer | The printer you pick in the Print dialog | System Settings > Printers & Scanners | Built into macOS (CUPS) |

All commands below are typed in **Terminal**. The project folder is `~/Downloads/secureprint`.

## Quick way: one script

```bash
cd ~/Downloads/secureprint
scripts/secureprint-mac.sh status     # what's running, and jobs waiting
scripts/secureprint-mac.sh stop       # stop capture, website and API
scripts/secureprint-mac.sh start      # start API, website and capture
scripts/secureprint-mac.sh restart    # stop, then start
scripts/secureprint-mac.sh logs       # watch the logs live (Control + C to quit)
```

With the script, the API and the website run in the background, so no Terminal windows need to stay open. Their logs are in `~/.secureprint/api.log` and `~/.secureprint/web.log`. After a Mac restart, run `scripts/secureprint-mac.sh start` once.

The sections below do the same things by hand.

---

## 1. Stop everything

### Stop the API server and the website

If you can see the Terminal windows they are running in, click each one and press **Control + C**.

If you can't find those windows (for example, Claude started them), run this instead:

```bash
lsof -ti tcp:8000 -sTCP:LISTEN | xargs kill      # stops the API server
lsof -ti tcp:3000 -sTCP:LISTEN | xargs kill      # stops the website
```

If nothing is running on that port, the command prints nothing or a small usage message. That is fine. The `-sTCP:LISTEN` part matters: without it, the command would also stop any app that is connected to the server, such as your web browser.

### Stop the print capture

The capture restarts itself if it is killed, so stop it through macOS:

```bash
launchctl bootout gui/$(id -u)/lk.secureprint.capture
```

It stays stopped until you start it again (step 2) or until you next log in. To stop it from starting at login too, see "Remove SecurePrint completely" below.

### Pause the printer (optional)

```bash
cupsdisable SecurePrint
```

Jobs sent to the printer now wait in the queue instead of being captured. Leaving the printer as it is also works: with the capture stopped, jobs simply wait.

### Check that everything is stopped

```bash
lsof -i :8000 -i :3000 -i :8001
```

No output means all three are stopped.

---

## 2. Start everything again

Do this in order: the server first, because the capture and the website both need it.

### Start the API server (Terminal window 1)

```bash
cd ~/Downloads/secureprint
make api-dev
```

Wait until it prints `Application startup complete`. Leave this window open. Closing it stops the server.

Check it from another window:

```bash
curl http://localhost:8000/api/v1/health
```

It should answer with a short line that includes `ok`.

### Start the website (Terminal window 2)

Open a new Terminal window (**Command + N**):

```bash
cd ~/Downloads/secureprint
make web-dev
```

Wait for `Ready`, then open http://localhost:3000 in Safari or Chrome and sign in. Leave this window open too.

### Start the print capture

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/lk.secureprint.capture.plist
```

If it says the service is already loaded, restart it instead:

```bash
launchctl kickstart -k gui/$(id -u)/lk.secureprint.capture
```

Check that it is listening:

```bash
lsof -i :8001
```

You should see a `Python` line.

### Resume the printer (only if you paused it)

```bash
cupsenable SecurePrint
```

### Test it

Print any document to **SecurePrint Protected Printer**. A public document is saved straight to `~/Desktop/SecurePrint Released`. A document with salaries or ID numbers shows the security alert first.

---

## 3. After you restart the Mac

The print capture and the printer start by themselves. The API server and the website do not, so open two Terminal windows and run `make api-dev` and `make web-dev` as in step 2.

If you print while the server is off, the job waits in the Mac's print queue with the message "Waiting for the SecurePrint server", and a notification tells you so. Start the server and the job is checked and printed by itself. Nothing is printed unchecked.

---

## 4. If something goes wrong

| Problem | What to do |
|---|---|
| `make api-dev` says the address is already in use | The old server is still running. Run `lsof -ti tcp:8000 -sTCP:LISTEN \| xargs kill`, then try again. |
| `make web-dev` says port 3000 is in use | Run `lsof -ti tcp:3000 -sTCP:LISTEN \| xargs kill`, then try again. |
| Printing does nothing, no alert | Check the capture with `lsof -i :8001`. If there is no output, start it (step 2). |
| A job sits in the queue saying "Waiting for the SecurePrint server" | Start the API server (step 2). The job then goes through by itself. |
| The queue says "SecurePrint access token rejected" | Create a new token on the Tokens page, put it in `~/.config/secureprint/agent.conf` as `API_TOKEN=`, then run `scripts/secureprint-mac.sh restart`. |
| You want to see what the capture did | `tail -50 ~/.secureprint/capture.log` |
| Jobs are stuck in the printer queue | `lpstat -o SecurePrint` lists them. `cancel -a SecurePrint` clears them. |
| You changed `capture.py` or `ipp_receiver.py` in the project | Run `bash apps/linux-agent/setup-printer-mac.sh` again from the project folder. It copies the new version and restarts the capture. It asks for your Mac password to recreate the printer. |

---

## 5. Remove SecurePrint completely

```bash
cd ~/Downloads/secureprint/apps/linux-agent
bash setup-printer-mac.sh --uninstall
```

This stops the capture, stops it starting at login and removes the printer (it asks for your Mac password). Your settings in `~/.config/secureprint` are kept. Stop the server and the website as in step 1. To install again later, run `bash setup-printer-mac.sh`.

---

## 6. Ending the Claude session on your Mac

Claude has been working on your Mac through a Remote Control session. To end it, tell Claude in the project thread to stop it, or close the Terminal window it runs in. If Claude started the API server and website, ending the session may stop them too. Start them again with step 2.
