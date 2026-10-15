"""API-level tests for direct (agent-free) network printer management."""
from __future__ import annotations

import socket
import threading

from tests.conftest import make_pdf
from tests.test_api_jobs import poll_job, upload


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


def test_staff_can_list_but_not_manage_printers(staff_client, admin_client):
    resp = admin_client.post(
        "/api/v1/printers", json={"name": "Office Printer", "protocol": "SOCKET", "host": "127.0.0.1", "port": 9100}
    )
    assert resp.status_code == 201

    list_resp = staff_client.get("/api/v1/printers")
    assert list_resp.status_code == 200
    assert any(p["name"] == "Office Printer" for p in list_resp.json())

    create_resp = staff_client.post(
        "/api/v1/printers", json={"name": "Should Fail", "protocol": "SOCKET", "host": "127.0.0.1", "port": 9100}
    )
    assert create_resp.status_code == 403


def test_printer_test_connection_reports_real_status(admin_client):
    server = _CapturingSocketServer()
    server.start()
    try:
        create_resp = admin_client.post(
            "/api/v1/printers",
            json={"name": "Real Socket Printer", "protocol": "SOCKET", "host": "127.0.0.1", "port": server.port},
        )
        printer_id = create_resp.json()["id"]

        test_resp = admin_client.post(f"/api/v1/printers/{printer_id}/test")
        assert test_resp.status_code == 200
        assert test_resp.json()["ok"] is True

        printers = admin_client.get("/api/v1/printers").json()
        updated = next(p for p in printers if p["id"] == printer_id)
        assert updated["status"] == "ONLINE"
        assert updated["last_tested_at"] is not None
    finally:
        server.stop()


def test_job_print_delivers_directly_to_network_printer_no_agent(staff_client, admin_client, tmp_path):
    server = _CapturingSocketServer()
    server.start()
    try:
        printer_resp = admin_client.post(
            "/api/v1/printers",
            json={"name": "Direct Network Printer", "protocol": "SOCKET", "host": "127.0.0.1", "port": server.port},
        )
        printer_id = printer_resp.json()["id"]

        job_id = upload(staff_client, tmp_path, ["Plain public content, nothing sensitive here."])
        poll_job(staff_client, job_id, ["READY"])

        print_resp = staff_client.post(f"/api/v1/jobs/{job_id}/print", json={"printer_id": printer_id})
        assert print_resp.status_code == 200
        assert print_resp.json()["status"] == "COMPLETED"

        server.join(timeout=2)
        assert server.received.startswith(b"%PDF")
    finally:
        server.stop()


def test_job_print_fails_closed_when_printer_unreachable(staff_client, admin_client, tmp_path):
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    free_port = probe.getsockname()[1]
    probe.close()

    printer_resp = admin_client.post(
        "/api/v1/printers",
        json={"name": "Unreachable Printer", "protocol": "SOCKET", "host": "127.0.0.1", "port": free_port},
    )
    printer_id = printer_resp.json()["id"]

    job_id = upload(staff_client, tmp_path, ["Plain public content, nothing sensitive here."])
    poll_job(staff_client, job_id, ["READY"])

    print_resp = staff_client.post(f"/api/v1/jobs/{job_id}/print", json={"printer_id": printer_id})
    assert print_resp.status_code == 502

    job = staff_client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "READY"  # never claimed COMPLETED for a failed delivery
