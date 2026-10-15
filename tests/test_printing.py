"""Tests for direct network printing (spec-replacement for the removed
print agent): a local TCP server stands in for a raw AppSocket printer, and a
local HTTP server speaking minimal IPP stands in for an IPP printer - both
exercised through the real wire protocol, not mocked at the Python level."""
from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from apps.api.services import printing


# ---------------------------------------------------------------------------
# Raw socket (AppSocket / JetDirect) printer stand-in
# ---------------------------------------------------------------------------


class _CapturingSocketServer(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.received = b""

    def run(self):
        conn, _ = self.sock.accept()
        with conn:
            while chunk := conn.recv(4096):
                self.received += chunk

    def stop(self):
        self.sock.close()


def test_socket_printer_connection_test_succeeds():
    server = _CapturingSocketServer()
    server.start()
    try:
        result = printing.test_socket_printer("127.0.0.1", server.port)
        assert result.ok is True
        assert "succeeded" in result.message
    finally:
        server.stop()


def test_socket_printer_connection_test_fails_when_nothing_listening():
    # Bind and immediately close to get a port nothing is listening on
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    free_port = probe.getsockname()[1]
    probe.close()

    result = printing.test_socket_printer("127.0.0.1", free_port, timeout=1)
    assert result.ok is False


def test_print_via_socket_streams_full_document_bytes():
    server = _CapturingSocketServer()
    server.start()
    try:
        payload = b"%PDF-1.4 fake sanitized document bytes for the printer"
        printing.print_via_socket("127.0.0.1", server.port, payload, timeout=5)
        server.join(timeout=2)
        assert server.received == payload
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# IPP printer stand-in - a real HTTP server that speaks minimal IPP
# ---------------------------------------------------------------------------


class _IPPTestServer(threading.Thread):
    """Speaks just enough IPP/1.1 to answer Get-Printer-Attributes and
    Print-Job, and records exactly what it received for assertions."""

    def __init__(self, fail: bool = False):
        super().__init__(daemon=True)
        self.fail = fail
        self.last_request_body: bytes | None = None
        handler = self._make_handler()
        self.httpd = HTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]

    def _make_handler(self_outer):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                self_outer.last_request_body = body

                status_code = 0x0500 if self_outer.fail else 0x0000
                resp = bytes([1, 1]) + status_code.to_bytes(2, "big") + (1).to_bytes(4, "big")
                resp += bytes([0x01])
                resp += printing._pack_attr(printing.TAG_CHARSET, "attributes-charset", b"utf-8")
                resp += printing._pack_attr(printing.TAG_NATURAL_LANGUAGE, "attributes-natural-language", b"en")
                resp += bytes([0x04])
                resp += printing._pack_attr(printing.TAG_ENUM, "printer-state", (3).to_bytes(4, "big"))
                resp += printing._pack_attr(printing.TAG_KEYWORD, "printer-state-reasons", b"none")
                resp += bytes([0x03])

                self.send_response(200)
                self.send_header("Content-Type", "application/ipp")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)

            def log_message(self, format, *args):  # noqa: A002 - silence test server logging
                pass

        return Handler

    def run(self):
        self.httpd.serve_forever(poll_interval=0.05)

    def stop(self):
        self.httpd.shutdown()


@pytest.fixture()
def ipp_server():
    server = _IPPTestServer()
    server.start()
    yield server
    server.stop()


@pytest.fixture()
def failing_ipp_server():
    server = _IPPTestServer(fail=True)
    server.start()
    yield server
    server.stop()


def test_ipp_printer_connection_test_reports_idle_state(ipp_server):
    result = printing.test_ipp_printer("127.0.0.1", ipp_server.port, "/ipp/print", use_tls=False)
    assert result.ok is True
    assert "idle" in result.message


def test_ipp_printer_connection_test_surfaces_error_status(failing_ipp_server):
    result = printing.test_ipp_printer("127.0.0.1", failing_ipp_server.port, "/ipp/print", use_tls=False)
    assert result.ok is False


def test_print_via_ipp_sends_document_bytes_and_succeeds(ipp_server):
    pdf_bytes = b"%PDF-1.4 fake sanitized document"
    printing.print_via_ipp("127.0.0.1", ipp_server.port, "/ipp/print", False, pdf_bytes, job_name="SP-TEST")

    assert ipp_server.last_request_body is not None
    assert ipp_server.last_request_body.endswith(pdf_bytes)
    # The Print-Job operation-id (0x0002) must appear in the request header
    assert ipp_server.last_request_body[2:4] == (printing.OP_PRINT_JOB).to_bytes(2, "big")


def test_print_via_ipp_raises_on_printer_error(failing_ipp_server):
    with pytest.raises(printing.PrintDeliveryError):
        printing.print_via_ipp("127.0.0.1", failing_ipp_server.port, "/ipp/print", False, b"%PDF-1.4 x", job_name="SP-TEST")


def test_dispatch_by_protocol_socket(monkeypatch):
    calls = {}

    def fake_test(host, port, timeout=5):
        calls["socket"] = (host, port)
        return printing.ConnectionResult(True, "ok")

    monkeypatch.setattr(printing, "test_socket_printer", fake_test)
    result = printing.test_printer("SOCKET", "printer.local", 9100, "/ipp/print", False)
    assert result.ok is True
    assert calls["socket"] == ("printer.local", 9100)


def test_print_via_ipp_passes_copies_and_two_sided_to_the_printer(ipp_server):
    options = printing.PrintOptions(copies=3, sides="two-sided-long-edge")
    printing.print_via_ipp("127.0.0.1", ipp_server.port, "/ipp/print", False, b"%PDF-1.4 x", job_name="SP-TEST",
                           options=options)
    attrs = printing._parse_response(ipp_server.last_request_body)["attributes"]
    assert int.from_bytes(attrs["copies"][0], "big") == 3
    assert attrs["sides"] == [b"two-sided-long-edge"]


def test_print_via_ipp_sends_no_job_settings_by_default(ipp_server):
    printing.print_via_ipp("127.0.0.1", ipp_server.port, "/ipp/print", False, b"%PDF-1.4 x", job_name="SP-TEST")
    attrs = printing._parse_response(ipp_server.last_request_body)["attributes"]
    assert "copies" not in attrs and "sides" not in attrs


def test_socket_printer_gets_one_stream_per_copy():
    received = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(5)

    def accept_all():
        for _ in range(2):
            conn, _ = sock.accept()
            with conn:
                data = b""
                while chunk := conn.recv(4096):
                    data += chunk
                received.append(data)

    t = threading.Thread(target=accept_all, daemon=True)
    t.start()
    printing.print_via_socket("127.0.0.1", sock.getsockname()[1], b"%PDF-1.4 copy", copies=2)
    t.join(timeout=2)
    sock.close()
    assert received == [b"%PDF-1.4 copy", b"%PDF-1.4 copy"]
