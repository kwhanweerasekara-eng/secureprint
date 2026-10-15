# Putting SecurePrint on a friend's Mac

This is the whole setup on a Mac that has never had SecurePrint. It takes four parts: install two free programs, copy the project, start the server and website, then add the printer. Everything is typed in **Terminal** unless it says otherwise.

## Part 1. Install the programs SecurePrint needs (once)

1. **Python 3.12.** Download the macOS installer from python.org (Downloads, then Python 3.12) and run it. Use the python.org version, not Homebrew's, because the security alert window needs the Tkinter part that comes with it.
2. **Node.js.** Download the LTS installer from nodejs.org and run it. The website needs it.
3. **Apple's command line tools.** These give you `make`. Run this and click Install in the window that appears:

```bash
xcode-select --install
```

If it says they are already installed, that is fine.

Check all three:

```bash
python3.12 --version
node --version
make --version
```

Each one should print a version number.

## Part 2. Copy the project over

### Option A: copy the folder (simplest)

On **your** Mac, make a zip that leaves out the big, computer specific folders. Those get rebuilt on your friend's Mac, and copying them would break things.

```bash
cd ~/Downloads
zip -r secureprint.zip secureprint -x "secureprint/.venv/*" "*/node_modules/*" "*/.next/*" "secureprint/storage/*" "*/__pycache__/*" "secureprint/_backup*" "secureprint/.claude/*" "*.DS_Store"
```

This leaves out `storage`, so your friend starts with an empty database: no old print jobs and no audit history. The two demo accounts are created again automatically. It also leaves out the old backup folder and the settings Claude used on your Mac.

Send `secureprint.zip` to your friend (AirDrop, Google Drive or a USB stick). On their Mac, put it in Downloads and double click it, so they have `~/Downloads/secureprint`.

### Option B: through GitHub

If the project is in a GitHub repository your friend can open, they can download it instead:

```bash
cd ~/Downloads
git clone https://github.com/OWNER/REPOSITORY.git secureprint
```

Put in the real address of the repository. The latest work from this week (the new website design, the Mac printer and the control script) only reaches GitHub if someone uploads it first, so Option A is the safer choice right now.

## Part 3. Start the server and the website

```bash
cd ~/Downloads/secureprint
python3.12 -m venv .venv
./.venv/bin/pip install -r apps/api/requirements.txt
make install-web
```

The last two commands download libraries, so they need internet and can take a few minutes. After that, start everything:

```bash
scripts/secureprint-mac.sh start
```

This first time it says "Print capture is not installed". That is expected, because the printer is added in Part 4. Open http://localhost:3000 in Safari or Chrome and sign in with username `admin` and password `admin123`.

## Part 4. Add the SecurePrint printer

1. In the website, open **Tokens** in the top bar and create a new access token. Copy it.
2. Run the printer setup the first time:

```bash
cd ~/Downloads/secureprint/apps/linux-agent
PYTHON=python3.12 bash setup-printer-mac.sh
```

3. It creates a settings file and opens it in TextEdit. Find the line `API_TOKEN=`, paste the token right after the `=`, and save.
4. Run the same setup command again. This time it asks for the Mac's password (to add the printer) and finishes.
5. Test it: print any document and pick **SecurePrint Protected Printer**. A safe document lands in `~/Desktop/SecurePrint Released`. A document with salaries or ID numbers shows the security alert first.

## Every day after that

| What you want | Command (from `~/Downloads/secureprint`) |
|---|---|
| Start everything | `scripts/secureprint-mac.sh start` |
| Stop everything | `scripts/secureprint-mac.sh stop` |
| See what is running | `scripts/secureprint-mac.sh status` |

After the Mac restarts, run `scripts/secureprint-mac.sh start` once. The full stop and restart guide is in `docs/start-stop-mac.md`.

## If something goes wrong

| Problem | What to do |
|---|---|
| `python3.12: command not found` | Python 3.12 from python.org is not installed yet (Part 1). |
| `npm: command not found` | Node.js is not installed yet (Part 1). |
| The setup says there is no working Tkinter | Python came from Homebrew. Install it from python.org and run the setup again. |
| The alert says the server can't be reached | Run `scripts/secureprint-mac.sh start`. |
| macOS asks whether Python may accept incoming connections | Click Allow. It only listens on the Mac itself. |

## To remove it from their Mac

```bash
cd ~/Downloads/secureprint
scripts/secureprint-mac.sh stop
bash apps/linux-agent/setup-printer-mac.sh --uninstall
```

Then delete the `secureprint` folder.
