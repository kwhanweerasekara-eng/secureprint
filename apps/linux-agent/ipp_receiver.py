"""A minimal IPP printer that only listens on this computer (localhost).

It is used on macOS, where CUPS has no PDF-to-folder backend. The
"SecurePrint" printer is added as an IPP printer at
ipp://localhost:8001/ipp/print (setup-printer-mac.sh). CUPS turns each job
into a PDF and delivers it here. This receiver writes it into the spool folder
that capture.py watches, so the rest of the flow is the same as on Ubuntu.

Next to each PDF it writes a small JSON file with the print settings the user
chose (copies, two-sided, colour) and who printed it, so capture.py can pass
them on to the real printer and to the audit trail.

While capture.py can't check documents (server down, token rejected), the
printer reports that it is not accepting jobs and answers job requests with
server-error-busy. CUPS then keeps each job in the Mac's own print queue and
retries, so nothing is lost and nothing is printed unchecked.

Only the operations CUPS uses are implemented: Get-Printer-Attributes,
Validate-Job, Print-Job, Create-Job, Send-Document, Get-Job-Attributes,
Get-Jobs, Cancel-Job and Close-Job (RFC 8010/8011). Standard library only.
"""
from __future__ import annotations

import itertools
import json
import logging
import os
import re
import socket
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger("secureprint.ipp")

# Delimiter tags
OPERATION, JOB, END, PRINTER, UNSUPPORTED = 0x01, 0x02, 0x03, 0x04, 0x05
# Value tags
INTEGER, BOOLEAN, ENUM = 0x21, 0x22, 0x23
RESOLUTION, RANGE = 0x32, 0x33
TEXT, NAME, KEYWORD, URI, URI_SCHEME, CHARSET, LANGUAGE, MIME = 0x41, 0x42, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49

OPS = {
    0x0002: "Print-Job", 0x0004: "Validate-Job", 0x0005: "Create-Job", 0x0006: "Send-Document",
    0x0008: "Cancel-Job", 0x0009: "Get-Job-Attributes", 0x000A: "Get-Jobs", 0x000B: "Get-Printer-Attributes",
    0x003B: "Close-Job",
}
OK, BAD_REQUEST, NOT_FOUND, FORMAT_NOT_SUPPORTED = 0x0000, 0x0400, 0x0406, 0x040A
NOT_SUPPORTED, BUSY = 0x0501, 0x0507
JOB_PROCESSING, JOB_CANCELED, JOB_COMPLETED = 5, 7, 9
PRINTER_IDLE, PRINTER_STOPPED = 3, 5
MAX_COPIES = 99
SIDES = ("one-sided", "two-sided-long-edge", "two-sided-short-edge")
KEEP_JOBS = 200  # job records kept for Get-Job-Attributes


def _attr(tag: int, name: str, *values) -> bytes:
    out = b""
    for i, value in enumerate(values):
        if tag in (INTEGER, ENUM):
            raw = int(value).to_bytes(4, "big", signed=True)
        elif tag == BOOLEAN:
            raw = b"\x01" if value else b"\x00"
        elif tag == RESOLUTION:
            raw = value[0].to_bytes(4, "big") + value[1].to_bytes(4, "big") + bytes([3])  # dots per inch
        elif tag == RANGE:
            raw = value[0].to_bytes(4, "big") + value[1].to_bytes(4, "big")
        else:
            raw = str(value).encode()
        label = name.encode() if i == 0 else b""
        out += bytes([tag]) + len(label).to_bytes(2, "big") + label + len(raw).to_bytes(2, "big") + raw
    return out


def parse_request(data: bytes) -> tuple[int, int, dict[str, list[bytes]], bytes]:
    """Returns (operation, request id, operation/job attributes, document data)."""
    if len(data) < 9:
        raise ValueError("short IPP request")
    operation = int.from_bytes(data[2:4], "big")
    request_id = int.from_bytes(data[4:8], "big")
    attrs: dict[str, list[bytes]] = {}
    pos, last = 8, None
    while pos < len(data):
        tag = data[pos]
        pos += 1
        if tag == END:
            return operation, request_id, attrs, data[pos:]
        if tag <= 0x0F:
            last = None
            continue
        name_len = int.from_bytes(data[pos:pos + 2], "big")
        name = data[pos + 2:pos + 2 + name_len].decode(errors="replace")
        pos += 2 + name_len
        value_len = int.from_bytes(data[pos:pos + 2], "big")
        value = data[pos + 2:pos + 2 + value_len]
        pos += 2 + value_len
        if name:
            attrs.setdefault(name, []).append(value)
            last = name
        elif last:
            attrs[last].append(value)
    raise ValueError("IPP request has no end-of-attributes tag")


def safe_title(title: str) -> str:
    cleaned = re.sub(r"[^\w .()-]+", "_", title).strip(" ._")[:80]
    # Drop the source file's extension ("report.docx" -> "report"); capture.py adds .pdf.
    return re.sub(r"\.[A-Za-z0-9]{1,5}$", "", cleaned) or "document"


def print_settings(attrs: dict[str, list[bytes]]) -> dict:
    """The user's choices from the Print dialog, and who printed, as sent by CUPS."""
    def text(name: str) -> str:
        return attrs[name][0].decode(errors="replace") if name in attrs else ""

    def number(name: str, default: int) -> int:
        value = attrs.get(name, [b""])[0]
        return int.from_bytes(value, "big") if len(value) == 4 else default

    sides = text("sides")
    return {
        "copies": max(1, min(number("copies", 1), MAX_COPIES)),
        "sides": sides if sides in SIDES else "one-sided",
        "color": "monochrome" if text("print-color-mode") == "monochrome" else "color",
        "user": text("requesting-user-name"),
        "host": text("job-originating-host-name"),
        "document": text("document-name-supplied"),
    }


class Receiver:
    def __init__(self, spool: Path, port: int = 8001, gate: Callable[[], str | None] | None = None) -> None:
        """gate() returns None while jobs can be checked, otherwise the reason they
        must wait. It is called for every request, so it must be quick."""
        self.spool = spool
        self.port = port
        self.gate = gate or (lambda: None)
        self.ids = itertools.count(int(time.time()) % 100000)
        self.jobs: dict[int, dict] = {}
        self.lock = threading.Lock()
        self.servers: list[ThreadingHTTPServer] = []

    # ---- printer description ----------------------------------------------

    def printer_attributes(self, host: str) -> bytes:
        uri = f"ipp://{host}:{self.port}/ipp/print"
        waiting = self.gate()
        return b"".join([
            _attr(URI, "printer-uri-supported", uri),
            _attr(KEYWORD, "uri-security-supported", "none"),
            _attr(KEYWORD, "uri-authentication-supported", "none"),
            _attr(NAME, "printer-name", "SecurePrint"),
            _attr(TEXT, "printer-info", "SecurePrint - checked before printing"),
            _attr(TEXT, "printer-make-and-model", "SecurePrint DLP Virtual Printer"),
            _attr(TEXT, "printer-location", "This computer"),
            _attr(ENUM, "printer-state", PRINTER_STOPPED if waiting else PRINTER_IDLE),
            _attr(KEYWORD, "printer-state-reasons", "other-warning" if waiting else "none"),
            _attr(TEXT, "printer-state-message", waiting or "Ready"),
            _attr(BOOLEAN, "printer-is-accepting-jobs", not waiting),
            _attr(KEYWORD, "ipp-versions-supported", "1.1", "2.0"),
            _attr(ENUM, "operations-supported", *OPS),
            _attr(CHARSET, "charset-configured", "utf-8"),
            _attr(CHARSET, "charset-supported", "utf-8"),
            _attr(LANGUAGE, "natural-language-configured", "en"),
            _attr(LANGUAGE, "generated-natural-language-supported", "en"),
            _attr(MIME, "document-format-default", "application/pdf"),
            _attr(MIME, "document-format-supported", "application/pdf"),
            _attr(KEYWORD, "pdl-override-supported", "attempted"),
            _attr(KEYWORD, "compression-supported", "none"),
            _attr(INTEGER, "queued-job-count", 0),
            _attr(INTEGER, "printer-up-time", int(time.monotonic())),
            _attr(BOOLEAN, "color-supported", True),
            _attr(KEYWORD, "print-color-mode-supported", "color", "monochrome"),
            _attr(KEYWORD, "print-color-mode-default", "color"),
            # Copies and two-sided are passed on to the real printer at release,
            # so the PDF must arrive as one plain copy. Advertising them here
            # stops CUPS from repeating pages or padding with blank pages.
            _attr(KEYWORD, "sides-supported", *SIDES),
            _attr(KEYWORD, "sides-default", "one-sided"),
            _attr(RANGE, "copies-supported", (1, MAX_COPIES)),
            _attr(INTEGER, "copies-default", 1),
            _attr(ENUM, "print-quality-supported", 4),
            _attr(ENUM, "print-quality-default", 4),
            _attr(RESOLUTION, "printer-resolution-supported", (300, 300)),
            _attr(RESOLUTION, "printer-resolution-default", (300, 300)),
            _attr(KEYWORD, "media-supported", "iso_a4_210x297mm", "na_letter_8.5x11in"),
            _attr(KEYWORD, "media-ready", "iso_a4_210x297mm"),
            _attr(KEYWORD, "media-default", "iso_a4_210x297mm"),
            # Face-down, like a normal office printer. With face-up, CUPS sends
            # the pages in reverse order so the paper stack comes out right.
            _attr(KEYWORD, "output-bin-supported", "face-down"),
            _attr(KEYWORD, "output-bin-default", "face-down"),
            _attr(KEYWORD, "job-creation-attributes-supported", "copies", "media", "sides", "print-color-mode"),
        ])

    def job_attributes(self, host: str, job_id: int) -> bytes:
        job = self.jobs.get(job_id, {})
        state = job.get("state", JOB_PROCESSING)
        reason = {JOB_COMPLETED: "job-completed-successfully", JOB_CANCELED: "job-canceled-by-user"}.get(state, "none")
        return b"".join([
            _attr(INTEGER, "job-id", job_id),
            _attr(URI, "job-uri", f"ipp://{host}:{self.port}/ipp/print/{job_id}"),
            _attr(NAME, "job-name", job.get("name", "document")),
            _attr(ENUM, "job-state", state),
            _attr(KEYWORD, "job-state-reasons", reason),
        ])

    # ---- operations ---------------------------------------------------------

    def new_job(self, attrs: dict[str, list[bytes]]) -> int:
        job_id = next(self.ids)
        name = attrs["job-name"][0].decode(errors="replace") if "job-name" in attrs else "document"
        self.jobs[job_id] = {"name": name, "settings": print_settings(attrs), "data": b"", "state": JOB_PROCESSING}
        for old in list(self.jobs)[:-KEEP_JOBS]:
            del self.jobs[old]
        return job_id

    def save(self, job_id: int, data: bytes) -> int:
        job = self.jobs[job_id]
        if not data.startswith(b"%PDF"):
            log.warning("Job %s is not a PDF (starts %r) - discarded", job_id, data[:8])
            job["state"] = JOB_CANCELED
            return FORMAT_NOT_SUPPORTED
        title = safe_title(job["name"])
        final = self.spool / f"job_{job_id}-{title}.pdf"
        # The settings file is written first: capture.py only picks up *.pdf,
        # so when the PDF appears its settings are already there.
        _write_private(final.with_suffix(".json"), json.dumps(job["settings"]).encode())
        part = final.with_suffix(".part")
        _write_private(part, data)
        part.replace(final)  # never a half-written *.pdf
        job["state"] = JOB_COMPLETED
        s = job["settings"]
        log.info("Received print job %s (%s, %d bytes, copies=%d, %s, from %s)",
                 job_id, title, len(data), s["copies"], s["sides"], s["user"] or "unknown user")
        return OK

    def handle(self, body: bytes, host: str) -> bytes:
        try:
            operation, request_id, attrs, data = parse_request(body)
        except ValueError:
            return self.response(BAD_REQUEST, 0)

        def job_id() -> int:
            return int.from_bytes(attrs["job-id"][0], "big") if "job-id" in attrs else -1

        name = OPS.get(operation)
        if name == "Get-Printer-Attributes":
            return self.response(OK, request_id, PRINTER, self.printer_attributes(host))
        if name in ("Validate-Job", "Print-Job", "Create-Job"):
            waiting = self.gate()
            if waiting:
                # CUPS keeps the job in its queue and tries again later.
                log.info("%s held in the print queue: %s", name, waiting)
                return self.response(BUSY, request_id)
        if name == "Validate-Job":
            fmt = attrs.get("document-format", [b"application/pdf"])[0]
            return self.response(OK if fmt in (b"application/pdf", b"application/octet-stream") else FORMAT_NOT_SUPPORTED,
                                 request_id)
        if name in ("Print-Job", "Create-Job"):
            with self.lock:
                new_id = self.new_job(attrs)
                status = self.save(new_id, data) if name == "Print-Job" else OK
            return self.response(status, request_id, JOB, self.job_attributes(host, new_id))
        if name == "Send-Document":
            jid = job_id()
            with self.lock:
                job = self.jobs.get(jid)
                if job is None or job["state"] != JOB_PROCESSING:
                    return self.response(NOT_FOUND, request_id)
                job["data"] += data
                last = attrs.get("last-document", [b"\x01"])[0] == b"\x01"
                status = self.save(jid, job.pop("data")) if last else OK
            return self.response(status, request_id, JOB, self.job_attributes(host, jid))
        if name == "Get-Job-Attributes":
            jid = job_id()
            if jid not in self.jobs:
                return self.response(NOT_FOUND, request_id)
            return self.response(OK, request_id, JOB, self.job_attributes(host, jid))
        if name == "Cancel-Job":
            with self.lock:
                job = self.jobs.get(job_id())
                if job is not None and job["state"] == JOB_PROCESSING:
                    job["state"] = JOB_CANCELED
                    job.pop("data", None)
            return self.response(OK, request_id)
        if name in ("Get-Jobs", "Close-Job"):
            return self.response(OK, request_id)
        return self.response(NOT_SUPPORTED, request_id)

    @staticmethod
    def response(status: int, request_id: int, group: int | None = None, attrs: bytes = b"") -> bytes:
        out = bytes([2, 0]) + status.to_bytes(2, "big") + request_id.to_bytes(4, "big")
        out += bytes([OPERATION]) + _attr(CHARSET, "attributes-charset", "utf-8")
        out += _attr(LANGUAGE, "attributes-natural-language", "en")
        if group is not None:
            out += bytes([group]) + attrs
        return out + bytes([END])

    # ---- HTTP -------------------------------------------------------------------

    def start(self) -> None:
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/ipp":
                    self.send_error(400)
                    return
                if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
                    body = b""
                    while True:
                        size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                        if size == 0:
                            while self.rfile.readline() not in (b"\r\n", b"\n", b""):
                                pass
                            break
                        body += self.rfile.read(size)
                        self.rfile.readline()
                else:
                    body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                reply = receiver.handle(body, self.headers.get("Host", "localhost").rsplit(":", 1)[0] or "localhost")
                self.send_response(200)
                self.send_header("Content-Type", "application/ipp")
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

            def log_message(self, fmt: str, *args) -> None:
                log.debug("ipp %s", fmt % args)

        # Loopback only, IPv4 and IPv6 ("localhost" can resolve to either).
        for family, address in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
            server_class = type("Server", (ThreadingHTTPServer,), {"address_family": family, "daemon_threads": True})
            try:
                server = server_class((address, self.port), Handler)
            except OSError as exc:
                if family == socket.AF_INET:
                    raise SystemExit(f"Port {self.port} is already in use - is another capture running? ({exc})")
                continue
            self.servers.append(server)
            threading.Thread(target=server.serve_forever, daemon=True).start()
        log.info("SecurePrint printer receiver listening on localhost:%s", self.port)

    def stop(self) -> None:
        for server in self.servers:
            server.shutdown()
            server.server_close()


def _write_private(path: Path, data: bytes) -> None:
    """Writes a file only this user can read: it holds an unmasked document."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
