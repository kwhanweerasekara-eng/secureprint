"""Compliance report PDF: admin only, covers the requested dates, reports
counts and categories, and never contains a detected value."""
from datetime import datetime, timedelta

import fitz

from tests.test_virtual_printer_flow import SETTLED, _agent_headers, _capture, _poll

NIC = "200012345678"
ACCOUNT = "123456789012"


def _report_text(resp) -> str:
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers["content-disposition"]
    with fitz.open("pdf", resp.content) as doc:
        # flags=0: spell out "ff" and "fi" ligatures as plain letters
        return "\n".join(p.get_text(flags=0) for p in doc)


def test_report_is_admin_only(staff_client):
    assert staff_client.get("/api/v1/reports/compliance").status_code == 403


def test_report_summarises_jobs_without_values(client, staff_client, admin_client, tmp_path):
    headers = _agent_headers(staff_client)
    job_id = _capture(
        client, headers, tmp_path, [f"NIC: {NIC}", f"Bank Account Number: {ACCOUNT}", "Salary: 285,000"], filename="payroll.pdf"
    )
    detail = _poll(client, headers, job_id, SETTLED)
    assert detail["classification"] == "RESTRICTED"
    client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers)

    text = _report_text(admin_client.get("/api/v1/reports/compliance"))

    assert "SecurePrint Compliance Report" in text
    assert "Documents by classification level" in text
    assert "National identity numbers" in text
    assert "Bank account numbers" in text
    assert job_id in text  # listed under recent restricted documents
    assert "Cancelled" in text
    assert "staff" in text  # jobs per user
    # Never a detected value, and no en or em dashes.
    assert NIC not in text and ACCOUNT not in text and "285,000" not in text
    assert "–" not in text and "—" not in text


def test_report_respects_the_date_range(admin_client):
    long_ago = (datetime.utcnow() - timedelta(days=400)).date()
    resp = admin_client.get(f"/api/v1/reports/compliance?date_from={long_ago}&date_to={long_ago}")
    text = _report_text(resp)
    assert "None" in text  # no restricted documents that day
    assert long_ago.isoformat() in resp.headers["content-disposition"]


def test_report_rejects_a_backwards_range(admin_client):
    resp = admin_client.get("/api/v1/reports/compliance?date_from=2026-10-10&date_to=2026-10-01")
    assert resp.status_code == 400
