"""A pretend office printer for demonstrations.

Runs SecurePrint's own IPP printer receiver on another port and saves every job
it is sent as a readable PDF in a folder, so an audience can open what "came out
of the printer". Point SecurePrint's release at it (LOCAL_PRINTER in agent.conf,
or the dashboard's Printers page) to show a checked job going to a printer.

    python3 demo_printer.py [--port 8002] [--out "~/Desktop/SecurePrint Demo Printer"]

It accepts only PDF and listens only on this computer.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import threading
from pathlib import Path

import ipp_receiver
from ipp_receiver import Receiver, safe_title

log = logging.getLogger("demo-printer")


class DemoPrinter(Receiver):
    show = True

    def save(self, job_id: int, data: bytes) -> int:
        # The output folder is on the Desktop, where it is easily tidied away.
        self.spool.mkdir(parents=True, exist_ok=True)
        status = super().save(job_id, data)
        if status != ipp_receiver.OK:
            return status
        # The receiver writes a private job file and a settings file for
        # capture.py; a printer's output tray only needs the readable page.
        saved = self.spool / f"job_{job_id}-{safe_title(self.jobs[job_id]['name'])}.pdf"
        saved.with_suffix(".json").unlink(missing_ok=True)
        target = self.spool / f"{saved.name.split('-', 1)[1]}"
        n = 2
        while target.exists():
            target = self.spool / f"{saved.stem.split('-', 1)[1]} ({n}).pdf"
            n += 1
        saved.replace(target)
        os.chmod(target, 0o644)
        log.info("Printed %s", target.name)
        if self.show:
            # Like a page landing in the tray: show it straight away.
            subprocess.Popen(["open", str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--out", default="~/Desktop/SecurePrint Demo Printer")
    parser.add_argument("--no-open", action="store_true", help="only save each job, don't open it")
    args = parser.parse_args()
    DemoPrinter.show = not args.no_open

    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    DemoPrinter(out, args.port).start()
    log.info("Demo Office Printer saving jobs to %s", out)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        stop.wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
