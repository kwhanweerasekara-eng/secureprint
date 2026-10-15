#!/usr/bin/env python3
"""SecurePrint print capture for Ubuntu and macOS - the counterpart of
apps/windows-agent/capture.ps1 (proposal section 3.3, Table 4.2 secondary
target).

The "SecurePrint" CUPS printer writes every job as a PDF into the user's
spool folder. On Ubuntu it uses the cups-pdf backend (setup-printer.sh). On
macOS it is an IPP printer at ipp://localhost:8001/ipp/print, served by
ipp_receiver.py inside this script (setup-printer-mac.sh). This script runs in the user's desktop session, picks up each PDF,
sends it to the SecurePrint API with the user's Personal Access Token,
shows the security alert for CONFIDENTIAL / RESTRICTED jobs (Tkinter, as in
proposal Table 3.6), and releases only the processed PDF, either through a
printer managed by the server or to a local CUPS printer with `lp`.

It fails closed: if the server rejects the file, times out or blocks the
job, nothing is printed and the user is told why. While the server can't be
reached (or rejects the access token), new jobs wait in the computer's own
print queue and are checked as soon as it is back, so nothing is lost and
nothing is printed unchecked.

Standard library only. Configuration: ~/.config/secureprint/agent.conf
(see agent.conf.example) or the same names as environment variables.

    python3 capture.py              # normal use
    python3 capture.py --once       # process what is in the spool folder, then exit
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "secureprint" / "agent.conf"
DEFAULT_SPOOL = Path.home() / ".secureprint" / "spool"
WORK_DIR = Path.home() / ".secureprint" / "work"
SETTLED = {"AWAITING_DECISION", "READY", "BLOCKED", "FAILED", "CANCELLED"}

CATEGORY_LABELS = {
    "credential": "Password or credential",
    "api_key": "API key or secret",
    "card": "Payment card number",
    "bank_account": "Bank account number",
    "iban": "IBAN",
    "nic": "National identity number",
    "passport": "Passport number",
    "salary": "Salary value",
    "employee_id": "Employee identifier",
    "email": "Email address",
    "telephone": "Telephone number",
    "classification_marker": "Classification marker",
}

SIDES_LABELS = {"two-sided-long-edge": "two-sided", "two-sided-short-edge": "two-sided (short edge)"}

log = logging.getLogger("secureprint")


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

def load_config(path: Path = CONFIG_PATH) -> dict[str, str]:
    cfg: dict[str, str] = {}
    if path.exists():
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                cfg[key.strip()] = value.strip().strip('"')
    for key in ("SERVER_URL", "API_TOKEN", "SERVER_PRINTER", "LOCAL_PRINTER", "SPOOL_DIR", "VERDICT_TIMEOUT",
                "IPP_PORT", "RELEASE_DIR"):
        if os.environ.get(key):
            cfg[key] = os.environ[key]
    return cfg


# --------------------------------------------------------------------------
# User interface. Tkinter is imported lazily so the script also runs headless
# (--decide), e.g. in automated tests.
# --------------------------------------------------------------------------

class Ui:
    def __init__(self, forced_decision: str | None = None) -> None:
        self.forced = forced_decision
        self._root = None

    def _tk(self):
        """One hidden Tk root for the life of the process. Creating and destroying
        a new Tk() per dialog freezes on macOS (spinning cursor) from the second
        dialog on, so every window is a Toplevel of this root instead."""
        import tkinter as tk

        if self._root is None:
            self._root = tk.Tk()
            self._root.withdraw()
        return tk, self._root

    def pause(self, seconds: float) -> None:
        """Sleep while still answering the window system. Once Tk has started,
        macOS marks the process "not responding" if its events are not handled."""
        if self._root is None:
            time.sleep(seconds)
            return
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self._root.update()
            time.sleep(0.05)

    def notify(self, message: str) -> None:
        log.info("NOTICE %s", message)
        if self.forced is not None:
            return
        if platform.system() == "Darwin":
            script = f"display notification {json.dumps(message)} with title \"SecurePrint\""
            subprocess.run(["osascript", "-e", script], check=False)
        elif shutil.which("notify-send"):
            subprocess.run(["notify-send", "SecurePrint", message], check=False)

    def problem(self, title: str, message: str) -> None:
        log.warning("%s - %s", title, message)
        if self.forced is not None:
            return
        from tkinter import messagebox

        _tk, root = self._tk()
        messagebox.showwarning(f"SecurePrint - {title}", message, parent=root)
        root.update()

    def security_alert(self, job: dict, settings: dict | None = None) -> str:
        """Appendix C dialog. Returns "mask" or "cancel"; closing the window cancels."""
        if self.forced is not None:
            return self.forced
        tk, parent = self._tk()
        choice = {"value": "cancel"}
        root = tk.Toplevel(parent)
        root.title("SecurePrint - Document Security Alert")
        root.attributes("-topmost", True)
        root.resizable(False, False)
        frame = tk.Frame(root, padx=18, pady=16)
        frame.pack()

        colour = "firebrick" if job.get("classification") == "RESTRICTED" else "darkorange"
        tk.Label(frame, text="DOCUMENT SECURITY ALERT", font=("TkDefaultFont", 14, "bold"), fg=colour).pack(anchor="w")
        tk.Label(frame, text="Sensitive information was detected in this document.").pack(anchor="w", pady=(6, 8))
        pages = job.get("page_count") or 0
        copies = settings.get("copies", 1) if settings else 1
        layout = ", ".join(filter(None, [f"{pages} page{'s' if pages != 1 else ''}" if pages else "",
                                         f"{copies} copies" if copies > 1 else "",
                                         SIDES_LABELS.get(settings.get("sides", "") if settings else "", "")]))
        for text, bold in [(f"Document:  {job.get('original_filename')}" + (f"  ({layout})" if layout else ""), False),
                           (f"Risk score:  {job.get('risk_score')} of 100", False),
                           (f"Classification:  {job.get('classification')}", True)]:
            tk.Label(frame, text=text, font=("TkDefaultFont", 10, "bold" if bold else "normal")).pack(anchor="w")
        tk.Label(frame, text="Categories detected", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(10, 0))
        for d in sorted(job.get("detections", []), key=lambda d: -d["count"]):
            label = CATEGORY_LABELS.get(d["category"], d["category"].replace("_", " ").title())
            plural = "occurrence" if d["count"] == 1 else "occurrences"
            tk.Label(frame, text=f"    {label}  -  {d['count']} {plural}").pack(anchor="w")
        tk.Label(frame, wraplength=400, justify="left",
                 text="If you continue, the values listed above will be masked and a classification footer "
                      "will be applied to every page before printing.").pack(anchor="w", pady=(10, 12))

        def choose(value: str) -> None:
            choice["value"] = value
            root.destroy()

        buttons = tk.Frame(frame)
        buttons.pack(anchor="e")
        cancel = tk.Button(buttons, text="Cancel printing", command=lambda: choose("cancel"))
        cancel.pack(side="left", padx=4)
        tk.Button(buttons, text="Mask and print", command=lambda: choose("mask")).pack(side="left", padx=4)
        # No default button: Enter must not print by reflex. Esc and close cancel.
        root.bind("<Escape>", lambda _e: choose("cancel"))
        root.protocol("WM_DELETE_WINDOW", lambda: choose("cancel"))
        root.lift()
        root.focus_force()
        cancel.focus_set()
        parent.wait_window(root)
        parent.update()
        return choice["value"]


# --------------------------------------------------------------------------
# SecurePrint API
# --------------------------------------------------------------------------

class ApiError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status  # HTTP status, or None when the server could not be reached

    @property
    def means_wait(self) -> bool:
        """True when the job should wait for the server rather than be refused."""
        return self.status is None or self.status in (401, 403)


class Api:
    def __init__(self, server_url: str, token: str) -> None:
        self.base = server_url.rstrip("/")
        self.token = token

    def _request(self, method: str, path: str, body: bytes | None = None, content_type: str | None = None,
                 timeout: float = 90) -> bytes:
        req = urllib.request.Request(self.base + path, data=body, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        if content_type:
            req.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            try:
                detail = json.loads(detail).get("detail", detail)
            except ValueError:
                pass
            raise ApiError(f"the server refused it ({exc.code}): {detail}", exc.code) from exc
        except urllib.error.URLError as exc:
            raise ApiError(f"the server could not be reached ({exc.reason})") from exc
        except OSError as exc:  # timeouts and dropped connections
            raise ApiError(f"the server could not be reached ({exc})") from exc

    def json(self, method: str, path: str, payload: dict | None = None, timeout: float = 90):
        body = json.dumps(payload).encode() if payload is not None else None
        return json.loads(self._request(method, path, body, "application/json" if body else None, timeout) or b"null")

    def upload(self, pdf: Path, name: str, settings: dict) -> dict:
        boundary = uuid.uuid4().hex
        safe_name = name.replace('"', "_")
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{safe_name}\"\r\n"
                f"Content-Type: application/pdf\r\n\r\n").encode() + pdf.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        query = urllib.parse.urlencode({"source": "virtual_printer", "copies": settings["copies"],
                                        "print_user": settings["user"][:64], "client_host": settings["host"][:128]})
        raw = self._request("POST", f"/api/v1/documents/analyze?{query}", body,
                            f"multipart/form-data; boundary={boundary}", timeout=120)
        return json.loads(raw)

    def download(self, job_id: str, out: Path) -> None:
        out.write_bytes(self._request("GET", f"/api/v1/jobs/{job_id}/document?download=1"))


# --------------------------------------------------------------------------
# Capture and release
# --------------------------------------------------------------------------

class ServerWatch:
    """Checks every few seconds that the server answers and accepts the token.
    While it doesn't, the SecurePrint printer tells CUPS it is not accepting
    jobs, so new jobs wait in the print queue (ipp_receiver.Receiver gate)."""

    INTERVAL = 5

    def __init__(self, api: Api, ui: Ui) -> None:
        self.api = api
        self.ui = ui
        self.problem: str | None = None  # shown in the print queue while jobs wait
        self._wake = threading.Event()

    def gate(self) -> str | None:
        return self.problem

    def check(self) -> None:
        try:
            self.api.json("GET", "/api/v1/auth/me", timeout=5)
        except ApiError as exc:
            self.report(exc, recheck=False)
            return
        self._set(None)

    def report(self, exc: ApiError, recheck: bool = True) -> None:
        if exc.status in (401, 403):
            self._set("SecurePrint access token rejected - see agent.conf",
                      "SecurePrint rejected this computer's access token. Documents you print will wait in the "
                      "print queue. Create a new token on the Tokens page and put it in " + str(CONFIG_PATH) + ".")
        elif exc.status is None:
            self._set("Waiting for the SecurePrint server",
                      "The SecurePrint server can't be reached. Documents you print will wait in the print queue "
                      "and are checked as soon as it is back.")
        if recheck:
            self._wake.set()  # a job just failed: check again now rather than in INTERVAL seconds

    def _set(self, problem: str | None, notice: str = "") -> None:
        old, self.problem = self.problem, problem
        if problem and problem != old:
            log.warning("Holding print jobs: %s", problem)
            self.ui.notify(notice)
        elif old and not problem:
            log.info("Server is back - checking held print jobs")
            self.ui.notify("The SecurePrint server is back. Documents waiting to print are being checked now.")

    def start(self) -> None:
        def loop() -> None:
            while True:
                self._wake.wait(self.INTERVAL)
                self._wake.clear()
                self.check()

        threading.Thread(target=loop, daemon=True, name="server-watch").start()


class Capture:
    MAX_ATTEMPTS = 5  # uploads of one job that may fail before it is given up

    def __init__(self, cfg: dict[str, str], ui: Ui) -> None:
        if not cfg.get("SERVER_URL") or not cfg.get("API_TOKEN"):
            raise SystemExit(f"Set SERVER_URL and API_TOKEN in {CONFIG_PATH} (see agent.conf.example).")
        self.api = Api(cfg["SERVER_URL"], cfg["API_TOKEN"])
        self.ui = ui
        self.watch = ServerWatch(self.api, ui)
        self.spool = Path(cfg.get("SPOOL_DIR") or DEFAULT_SPOOL).expanduser()
        self.local_printer = cfg.get("LOCAL_PRINTER", "")
        self.release_dir = Path(cfg["RELEASE_DIR"]).expanduser() if cfg.get("RELEASE_DIR") else None
        self.timeout = float(cfg.get("VERDICT_TIMEOUT", "120"))
        self.sizes: dict[Path, int] = {}
        self.attempts: dict[Path, int] = {}
        self.server_printer = cfg.get("SERVER_PRINTER", "")
        self._printer_id: str | None = None
        if self.local_printer.lower() == "secureprint":
            raise SystemExit("LOCAL_PRINTER cannot be the SecurePrint printer itself - jobs would loop forever.")
        # The spool holds unmasked documents until they are checked: this user only.
        for folder in (self.spool, WORK_DIR):
            folder.mkdir(parents=True, exist_ok=True)
            folder.chmod(0o700)
        # macOS has no cups-pdf, so the SecurePrint printer delivers to a receiver
        # in this process instead. Ubuntu normally leaves IPP_PORT empty.
        default_port = "8001" if platform.system() == "Darwin" else ""
        self.ipp_port = int(cfg.get("IPP_PORT", default_port) or 0)

    def printer_id(self) -> str:
        """The SERVER_PRINTER's id, looked up when first needed (the server may
        be down when the capture starts)."""
        if self.server_printer and self._printer_id is None:
            for p in self.api.json("GET", "/api/v1/printers") or []:
                if self.server_printer in (p["id"], p["name"]):
                    log.info("Releasing checked jobs to server printer '%s'", p["name"])
                    self._printer_id = p["id"]
                    break
            else:
                raise ApiError(f"server printer '{self.server_printer}' is not on the web app's Printers page", 404)
        return self._printer_id or ""

    def ready_files(self) -> list[Path]:
        """PDFs that have been fully written: same size on two checks (cups-pdf
        writes in place; the IPP receiver renames finished files into place)."""
        ready = []
        for pdf in sorted(self.spool.glob("*.pdf")):
            size = pdf.stat().st_size
            if size > 0 and self.sizes.get(pdf) == size:
                ready.append(pdf)
                self.sizes.pop(pdf, None)
            else:
                self.sizes[pdf] = size
        return ready

    def wait(self, job_id: str, statuses: set[str]) -> dict | None:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            job = self.api.json("GET", f"/api/v1/jobs/{job_id}")
            if job["status"] in statuses:
                return job
            self.ui.pause(0.4)
        return None

    def handle(self, pdf: Path) -> str:
        """Processes one captured PDF. Returns the outcome, for logs and tests."""
        name = display_name(pdf)
        settings = read_settings(pdf)
        try:
            created = self.api.upload(pdf, name, settings)
        except ApiError as exc:
            self.attempts[pdf] = self.attempts.get(pdf, 0) + 1
            if exc.means_wait and self.attempts[pdf] < self.MAX_ATTEMPTS:
                # Keep the file in the spool; it is checked when the server is back.
                self.watch.report(exc)
                return "waiting"
            self.attempts.pop(pdf, None)
            discard(pdf)
            self.ui.problem("Not printed", f"'{name}' could not be checked by SecurePrint, so it was not printed: {exc}")
            return "not_checked"
        self.attempts.pop(pdf, None)
        discard(pdf)  # the captured file holds the unmasked document

        try:
            job = self.wait(created["id"], SETTLED)
            if job is None:
                self.ui.problem("Not printed", f"SecurePrint did not finish checking '{name}' in time, so it was not printed.")
                return "timeout"
            if job["status"] == "AWAITING_DECISION":
                choice = self.ui.security_alert(job, settings)
                log.info("User chose %s for %s (%s, score %s)", choice, job["id"], job["classification"], job["risk_score"])
                if choice != "mask":
                    self.api.json("POST", f"/api/v1/jobs/{job['id']}/cancel")
                    self.ui.notify(f"Printing of '{name}' was cancelled.")
                    return "cancelled"
                self.api.json("POST", f"/api/v1/jobs/{job['id']}/sanitize")
                job = self.wait(job["id"], {"READY", "BLOCKED", "FAILED"})
                if job is None:
                    self.ui.problem("Not printed", f"SecurePrint did not finish masking '{name}' in time, so it was not printed.")
                    return "timeout"
            if job["status"] == "READY":
                return self.release(job, settings)
            reason = job.get("status_message") or f"The job ended as {job['status']}."
            self.ui.problem("Print job blocked", f"'{name}' was not printed.\n\n{reason}")
            return "blocked"
        except ApiError as exc:
            self.ui.problem("Not printed", f"Something went wrong while handling '{name}', so it was not printed: {exc}")
            return "error"

    def release(self, job: dict, settings: dict) -> str:
        name = job["original_filename"]
        copies, sides = settings["copies"], settings["sides"]
        if self.server_printer:
            try:
                self.api.json("POST", f"/api/v1/jobs/{job['id']}/print",
                              {"printer_id": self.printer_id(), "copies": copies, "sides": sides})
            except ApiError as exc:
                self.ui.problem("Not printed", f"'{name}' is ready, but the server could not deliver it: {exc}")
                return "release_failed"
            self.ui.notify(f"'{name}' ({job['classification']}) was sent to the printer.")
            return "printed"
        if self.local_printer:
            out = WORK_DIR / f"{job['id']}-release.pdf"
            try:
                self.api.download(job["id"], out)
                # The user's Print dialog choices go to the real printer.
                subprocess.run(["lp", "-d", self.local_printer, "-t", name, "-n", str(copies), "-o", f"sides={sides}",
                                "-o", f"print-color-mode={settings['color']}", str(out)],
                               check=True, capture_output=True, text=True)
                self.api.json("POST", f"/api/v1/jobs/{job['id']}/print",
                              {"released_to": f"local printer '{self.local_printer}'", "copies": copies, "sides": sides})
            except (ApiError, subprocess.CalledProcessError, FileNotFoundError) as exc:
                self.ui.problem("Not printed", f"'{name}' is ready, but it could not be sent to '{self.local_printer}': {exc}")
                return "release_failed"
            finally:
                out.unlink(missing_ok=True)  # lp has already copied it into the CUPS spool
            self.ui.notify(f"'{name}' ({job['classification']}) was sent to {self.local_printer}.")
            return "printed"
        if self.release_dir:
            # No printer attached (e.g. a demo laptop): save the processed PDF and open it.
            self.release_dir.mkdir(parents=True, exist_ok=True)
            out = self.release_dir / f"{Path(name).stem} ({job['classification']}).pdf"
            try:
                self.api.download(job["id"], out)
                self.api.json("POST", f"/api/v1/jobs/{job['id']}/print", {"released_to": f"the folder {self.release_dir}"})
            except ApiError as exc:
                self.ui.problem("Not printed", f"'{name}' is ready, but it could not be saved: {exc}")
                return "release_failed"
            if self.ui.forced is None:
                opener = "open" if platform.system() == "Darwin" else "xdg-open"
                if shutil.which(opener):
                    subprocess.run([opener, str(out)], check=False)
            self.ui.notify(f"'{name}' ({job['classification']}) was saved to {out}.")
            return "saved"
        self.ui.problem("No printer set", f"'{name}' is ready, but no release printer is configured. Set SERVER_PRINTER, "
                                          f"LOCAL_PRINTER or RELEASE_DIR in {CONFIG_PATH}, or print it from the "
                                          f"SecurePrint web app.")
        return "held"

    def run(self, once: bool = False) -> None:
        log.info("SecurePrint print capture started - watching %s", self.spool)
        self.watch.check()
        if self.ipp_port:
            from ipp_receiver import Receiver
            Receiver(self.spool, self.ipp_port, gate=self.watch.gate).start()
        if not once:
            self.watch.start()
        while True:
            if self.watch.problem is None:
                for pdf in self.ready_files():
                    outcome = self.handle(pdf)
                    log.info("Captured %s: %s", pdf.name, outcome)
                    if outcome == "waiting":
                        break  # the rest wait for the server too
            if once and (self.watch.problem or not any(self.spool.glob("*.pdf"))):
                return
            self.ui.pause(0.5)


DEFAULT_SETTINGS = {"copies": 1, "sides": "one-sided", "color": "color", "user": "", "host": "", "document": ""}


def read_settings(pdf: Path) -> dict:
    """The Print dialog settings the IPP receiver saved next to the PDF. cups-pdf
    (Ubuntu) saves none, so its jobs print as one one-sided copy."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        settings.update(json.loads(pdf.with_suffix(".json").read_text()))
    except (OSError, ValueError):
        pass
    settings["copies"] = max(1, min(int(settings.get("copies") or 1), 99))
    if settings["sides"] not in ("one-sided", "two-sided-long-edge", "two-sided-short-edge"):
        settings["sides"] = "one-sided"
    return settings


def discard(pdf: Path) -> None:
    pdf.unlink(missing_ok=True)
    pdf.with_suffix(".json").unlink(missing_ok=True)


def display_name(pdf: Path) -> str:
    """cups-pdf names files "job_<n>-<title>.pdf" (Label 1); show the title."""
    stem = pdf.stem
    if stem.startswith("job_") and "-" in stem:
        stem = stem.split("-", 1)[1] or stem
    return f"{stem}.pdf"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true", help="process the spool folder once, then exit")
    parser.add_argument("--decide", choices=["mask", "cancel"], help="answer alerts without a window (testing)")
    args = parser.parse_args()
    log_dir = Path.home() / ".secureprint"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(log_dir / "capture.log")])
    Capture(load_config(), Ui(args.decide)).run(once=args.once)


if __name__ == "__main__":
    sys.exit(main())
