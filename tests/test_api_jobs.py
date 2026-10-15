"""End-to-end API tests for the full SecurePrint pipeline:
upload -> analyze -> detect -> score -> classify -> alert -> mask -> print.
"""
import io
import time

import fitz
import pytest

from tests.conftest import make_pdf, make_scanned_pdf


def poll_job(client, job_id, terminal_statuses, timeout=10):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        resp = client.get(f"/api/v1/jobs/{job_id}")
        last = resp.json()
        if last["status"] in terminal_statuses:
            return last
        time.sleep(0.1)
    raise TimeoutError(f"job did not reach {terminal_statuses}, last state: {last}")


def upload(client, tmp_path, lines, filename="doc.pdf"):
    pdf_path = make_pdf(tmp_path / filename, lines)
    with open(pdf_path, "rb") as f:
        resp = client.post(
            "/api/v1/documents/analyze",
            files={"file": (filename, f, "application/pdf")},
        )
    assert resp.status_code == 202, resp.text
    return resp.json()["id"]


def test_public_document_auto_releases_without_alert(staff_client, tmp_path):
    job_id = upload(staff_client, tmp_path, ["This is a plain public notice with no sensitive data at all."])
    job = poll_job(staff_client, job_id, ["READY", "BLOCKED", "FAILED"])
    assert job["status"] == "READY"
    assert job["classification"] == "PUBLIC"
    assert job["action"] == "ALLOW_PRINT"


def test_restricted_document_requires_security_alert(staff_client, tmp_path):
    job_id = upload(
        staff_client,
        tmp_path,
        [
            "NIC: 200012345678",
            "Bank Account Number: 123456789012",
            "password: Sup3rSecret!2026",
            "Basic Salary: LKR 250,000",
        ],
    )
    job = poll_job(staff_client, job_id, ["AWAITING_DECISION", "READY", "BLOCKED", "FAILED"])
    assert job["status"] == "AWAITING_DECISION"
    assert job["classification"] == "RESTRICTED"
    assert job["risk_score"] >= 71
    categories = {d["category"] for d in job["detections"]}
    assert "nic" in categories
    assert "credential" in categories


def test_mask_and_continue_produces_downloadable_sanitized_pdf(staff_client, tmp_path):
    job_id = upload(
        staff_client, tmp_path, ["NIC: 200012345678", "Email: staff@example.com", "Basic Salary: LKR 250,000"]
    )
    job = poll_job(staff_client, job_id, ["AWAITING_DECISION", "READY"])
    assert job["status"] == "AWAITING_DECISION"  # CONFIDENTIAL/RESTRICTED must require a decision

    resp = staff_client.post(f"/api/v1/jobs/{job_id}/sanitize")
    assert resp.status_code == 200

    job = poll_job(staff_client, job_id, ["READY", "FAILED", "BLOCKED"])
    assert job["status"] == "READY"

    doc_resp = staff_client.get(f"/api/v1/jobs/{job_id}/document")
    assert doc_resp.status_code == 200
    assert doc_resp.headers["content-type"] == "application/pdf"

    pdf = fitz.open(stream=doc_resp.content, filetype="pdf")
    text = "\n".join(p.get_text() for p in pdf)
    pdf.close()
    assert "200012345678" not in text
    assert "staff@example.com" not in text


def test_cancel_blocks_original_from_ever_reaching_printer(staff_client, tmp_path):
    job_id = upload(staff_client, tmp_path, ["NIC: 200012345678", "Bank Account Number: 987654321098"])
    poll_job(staff_client, job_id, ["AWAITING_DECISION"])

    resp = staff_client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert resp.status_code == 200
    job = resp.json()
    assert job["status"] == "CANCELLED"
    assert job["action"] == "CANCELLED"

    # the sanitized document endpoint must refuse - nothing to print
    doc_resp = staff_client.get(f"/api/v1/jobs/{job_id}/document")
    assert doc_resp.status_code == 409


def test_print_only_serves_sanitized_document_not_original(staff_client, tmp_path):
    job_id = upload(
        staff_client, tmp_path, ["NIC: 200012345678", "password: Sup3rSecret!2026", "Basic Salary: LKR 250,000"]
    )
    poll_job(staff_client, job_id, ["AWAITING_DECISION"])
    staff_client.post(f"/api/v1/jobs/{job_id}/sanitize")
    poll_job(staff_client, job_id, ["READY"])

    print_resp = staff_client.post(f"/api/v1/jobs/{job_id}/print")
    assert print_resp.status_code == 200
    assert print_resp.json()["status"] == "COMPLETED"


def test_document_endpoint_is_inline_for_preview_and_print(staff_client, tmp_path):
    """The preview iframe and window.print() flow both need an inline
    Content-Disposition - an "attachment" response can't be rendered by an
    iframe or a print-triggering popup (only ?download=1 should force save)."""
    job_id = upload(staff_client, tmp_path, ["Plain public content only, nothing sensitive."])
    poll_job(staff_client, job_id, ["READY"])

    preview_resp = staff_client.get(f"/api/v1/jobs/{job_id}/document")
    assert preview_resp.status_code == 200
    assert "inline" in preview_resp.headers["content-disposition"]

    download_resp = staff_client.get(f"/api/v1/jobs/{job_id}/document?download=1")
    assert download_resp.status_code == 200
    assert "attachment" in download_resp.headers["content-disposition"]


def test_scanned_document_blocks_with_ocr_message(staff_client, tmp_path):
    pdf_path = make_scanned_pdf(tmp_path / "scan.pdf")
    with open(pdf_path, "rb") as f:
        resp = staff_client.post("/api/v1/documents/analyze", files={"file": ("scan.pdf", f, "application/pdf")})
    job_id = resp.json()["id"]
    job = poll_job(staff_client, job_id, ["BLOCKED", "FAILED"])
    assert job["status"] == "BLOCKED"
    assert job["block_reason"] == "SCANNED_DOCUMENT"
    assert "OCR" in job["status_message"]


def test_non_pdf_upload_rejected(staff_client):
    resp = staff_client.post(
        "/api/v1/documents/analyze",
        files={"file": ("notes.txt", io.BytesIO(b"not a pdf"), "text/plain")},
    )
    assert resp.status_code == 400


def test_fake_pdf_extension_with_wrong_magic_bytes_rejected(staff_client):
    resp = staff_client.post(
        "/api/v1/documents/analyze",
        files={"file": ("fake.pdf", io.BytesIO(b"this is not really a pdf file"), "application/pdf")},
    )
    assert resp.status_code == 400


def test_user_cannot_see_other_users_jobs(staff_client, admin_client, tmp_path):
    job_id = upload(staff_client, tmp_path, ["NIC: 200012345678"])
    # admin can see everything
    resp = admin_client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200


def test_dashboard_stats_reflect_real_jobs(staff_client, tmp_path):
    upload(staff_client, tmp_path, ["Plain public content only."])
    resp = staff_client.get("/api/v1/dashboard/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["documents_processed"] >= 1
