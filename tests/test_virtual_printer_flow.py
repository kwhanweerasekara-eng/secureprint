"""The calls the Windows agent makes for a job captured from the SecurePrint
virtual printer: upload with a Personal Access Token, wait for the verdict,
then cancel or mask and release. Covers test cases T01, T04 and T08 of the
proposal's evaluation plan from the agent's side."""
import fitz

from tests.conftest import make_pdf
from tests.test_api_jobs import poll_job

SETTLED = {"AWAITING_DECISION", "READY", "BLOCKED", "FAILED"}


def _agent_headers(staff_client):
    raw_token = staff_client.post("/api/v1/tokens", json={"name": "Print capture"}).json()["token"]
    return {"Authorization": f"Bearer {raw_token}"}


def _capture(client, headers, tmp_path, lines, filename="captured.pdf"):
    pdf_path = make_pdf(tmp_path / filename, lines)
    with open(pdf_path, "rb") as f:
        resp = client.post(
            "/api/v1/documents/analyze?source=virtual_printer",
            files={"file": (filename, f, "application/pdf")},
            headers=headers,
        )
    assert resp.status_code == 202, resp.text
    return resp.json()["id"]


def _poll(client, headers, job_id, statuses):
    client.headers.update(headers)
    return poll_job(client, job_id, statuses)


def test_captured_job_is_audited_as_virtual_printer(client, staff_client, tmp_path):
    headers = _agent_headers(staff_client)
    job_id = _capture(client, headers, tmp_path, ["Office party on Friday."])
    detail = _poll(client, headers, job_id, SETTLED)

    received = [e for e in detail["events"] if e["event_type"] == "JOB_RECEIVED"]
    assert received and received[0]["event_metadata"]["source"] == "virtual_printer"
    assert "virtual printer" in received[0]["message"]


def test_unknown_source_is_rejected(client, staff_client, tmp_path):
    headers = _agent_headers(staff_client)
    pdf_path = make_pdf(tmp_path / "x.pdf", ["hello"])
    with open(pdf_path, "rb") as f:
        resp = client.post(
            "/api/v1/documents/analyze?source=somewhere",
            files={"file": ("x.pdf", f, "application/pdf")},
            headers=headers,
        )
    assert resp.status_code == 400


def test_public_capture_releases_without_a_decision(client, staff_client, tmp_path):
    headers = _agent_headers(staff_client)
    job_id = _capture(client, headers, tmp_path, ["Office party on Friday."])
    detail = _poll(client, headers, job_id, SETTLED)
    assert detail["classification"] == "PUBLIC"
    assert detail["status"] == "READY"

    released = client.post(f"/api/v1/jobs/{job_id}/print", json={}, headers=headers)
    assert released.status_code == 200
    assert released.json()["status"] == "COMPLETED"


def test_cancel_from_desktop_dialog_is_audited_and_nothing_is_released(client, staff_client, tmp_path):
    headers = _agent_headers(staff_client)
    job_id = _capture(
        client,
        headers,
        tmp_path,
        ["NIC: 200012345678", "Bank Account Number: 123456789012", "Salary: 285,000"],
    )
    detail = _poll(client, headers, job_id, SETTLED)
    assert detail["status"] == "AWAITING_DECISION"
    assert detail["classification"] == "RESTRICTED"

    resp = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"

    detail = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    assert any(e["event_type"] == "DECISION_CANCEL" for e in detail["events"])
    assert client.get(f"/api/v1/jobs/{job_id}/document", headers=headers).status_code == 409
    assert client.post(f"/api/v1/jobs/{job_id}/print", json={}, headers=headers).status_code == 409


def test_mask_and_print_from_desktop_dialog(client, staff_client, tmp_path):
    headers = _agent_headers(staff_client)
    job_id = _capture(
        client,
        headers,
        tmp_path,
        ["NIC: 200012345678", "Bank Account Number: 123456789012", "Salary: 285,000"],
    )
    _poll(client, headers, job_id, SETTLED)

    assert client.post(f"/api/v1/jobs/{job_id}/sanitize", headers=headers).status_code == 200
    detail = _poll(client, headers, job_id, {"READY", "FAILED"})
    assert detail["status"] == "READY"

    doc = client.get(f"/api/v1/jobs/{job_id}/document?download=1", headers=headers)
    assert doc.status_code == 200
    assert doc.content.startswith(b"%PDF-")
    with fitz.open(stream=doc.content, filetype="pdf") as pdf:
        text = "".join(page.get_text() for page in pdf)
    assert "200012345678" not in text
    assert "123456789012" not in text
    # Appendix B: a salary with no currency prefix is masked, its label kept.
    assert "285,000" not in text
    assert "Salary" in text

    released = client.post(f"/api/v1/jobs/{job_id}/print", json={}, headers=headers)
    assert released.json()["status"] == "COMPLETED"


def test_t05_a_single_real_password_makes_the_document_restricted(client, staff_client, tmp_path):
    # Proposal test case T05: a credential alone scores 40 (Internal by score),
    # but a real password must put the page in the Restricted band.
    headers = _agent_headers(staff_client)
    job_id = _capture(client, headers, tmp_path, ["Server handover", "password: Winter@2026"])
    detail = _poll(client, headers, job_id, SETTLED)
    assert detail["risk_score"] == 40
    assert detail["classification"] == "RESTRICTED"
    classified = [e for e in detail["events"] if e["event_type"] == "CLASSIFIED"][0]
    assert classified["event_metadata"]["score_classification"] == "INTERNAL"


def test_the_bare_word_password_does_not_raise_the_level(client, staff_client, tmp_path):
    headers = _agent_headers(staff_client)
    job_id = _capture(client, headers, tmp_path, ["Never share your password with anyone."])
    detail = _poll(client, headers, job_id, SETTLED)
    assert detail["classification"] != "RESTRICTED"


def test_capture_records_who_printed_and_the_copies(client, staff_client, tmp_path):
    headers = _agent_headers(staff_client)
    pdf_path = make_pdf(tmp_path / "rota.pdf", ["Office party on Friday."])
    with open(pdf_path, "rb") as f:
        resp = client.post(
            "/api/v1/documents/analyze?source=virtual_printer&copies=3&print_user=vinu&client_host=vinus-mac",
            files={"file": ("rota.pdf", f, "application/pdf")},
            headers=headers,
        )
    assert resp.status_code == 202
    detail = _poll(client, headers, resp.json()["id"], SETTLED)
    received = [e for e in detail["events"] if e["event_type"] == "JOB_RECEIVED"][0]
    assert "printed by vinu on vinus-mac" in received["message"]
    assert "3 copies" in received["message"]
    assert received["event_metadata"]["print_user"] == "vinu"


def test_capture_release_is_audited_with_where_it_went(client, staff_client, tmp_path):
    headers = _agent_headers(staff_client)
    job_id = _capture(client, headers, tmp_path, ["Office party on Friday."])
    _poll(client, headers, job_id, SETTLED)
    released = client.post(f"/api/v1/jobs/{job_id}/print", headers=headers,
                           json={"released_to": "local printer 'Office_HP'", "copies": 2, "sides": "two-sided-long-edge"})
    assert released.status_code == 200
    detail = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
    event = [e for e in detail["events"] if e["event_type"] == "RELEASED_TO_PRINTER"][0]
    assert event["message"] == ("Sanitized document released by the SecurePrint print capture to "
                                "local printer 'Office_HP' (2 copies, two-sided)")
    assert "Web Analysis Mode" not in event["message"]


def test_copies_out_of_range_are_refused(client, staff_client, tmp_path):
    headers = _agent_headers(staff_client)
    job_id = _capture(client, headers, tmp_path, ["Office party on Friday."])
    _poll(client, headers, job_id, SETTLED)
    assert client.post(f"/api/v1/jobs/{job_id}/print", json={"copies": 500}, headers=headers).status_code == 422
