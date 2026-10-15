"""Tests for Personal Access Tokens (the Windows agent's credential) and the
real-time security-alert feed it consumes."""
from __future__ import annotations

import time

from tests.conftest import make_pdf
from tests.test_api_jobs import poll_job, upload


def test_create_token_returns_raw_value_once(staff_client):
    resp = staff_client.post("/api/v1/tokens", json={"name": "Office PC"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["token"].startswith("sp_pat_")
    assert body["token_prefix"] == body["token"][:13]

    # the list endpoint must never expose the raw token again
    listing = staff_client.get("/api/v1/tokens").json()
    assert all("token" not in t for t in listing)
    assert any(t["id"] == body["id"] and t["name"] == "Office PC" for t in listing)


def test_bearer_token_authenticates_like_the_cookie(client, staff_client):
    created = staff_client.post("/api/v1/tokens", json={"name": "Agent"}).json()
    raw_token = created["token"]

    # a fresh, cookie-less client using only the bearer token
    resp = client.get("/api/v1/jobs", headers={"Authorization": f"Bearer {raw_token}"})
    assert resp.status_code == 200


def test_revoked_token_is_rejected(client, staff_client):
    created = staff_client.post("/api/v1/tokens", json={"name": "Agent"}).json()
    raw_token = created["token"]
    staff_client.delete(f"/api/v1/tokens/{created['id']}")

    resp = client.get("/api/v1/jobs", headers={"Authorization": f"Bearer {raw_token}"})
    assert resp.status_code == 401


def test_token_belongs_to_its_own_user_only(staff_client, admin_client):
    created = staff_client.post("/api/v1/tokens", json={"name": "Mine"}).json()
    # admin cannot revoke staff's token
    resp = admin_client.delete(f"/api/v1/tokens/{created['id']}")
    assert resp.status_code == 404


def test_recent_alerts_endpoint_reports_restricted_job(staff_client, tmp_path):
    from datetime import datetime, timedelta

    since = (datetime.utcnow() - timedelta(seconds=5)).isoformat()
    job_id = upload(
        staff_client, tmp_path, ["NIC: 200012345678", "password: Sup3rSecret!2026", "Basic Salary: LKR 250,000"]
    )
    poll_job(staff_client, job_id, ["AWAITING_DECISION"])

    resp = staff_client.get(f"/api/v1/notifications/recent?since={since}")
    assert resp.status_code == 200
    alerts = resp.json()["alerts"]
    matching = [a for a in alerts if a["job_id"] == job_id]
    assert len(matching) == 1
    alert = matching[0]
    assert alert["event_type"] == "AWAITING_DECISION"
    assert alert["classification"] == "RESTRICTED"
    assert alert["risk_score"] == 90  # nic(30) + credential(40) + salary(20)
    assert alert["filename"]
    assert "nic" in alert["categories"]


def test_recent_alerts_excludes_public_documents(staff_client, tmp_path):
    from datetime import datetime, timedelta

    since = (datetime.utcnow() - timedelta(seconds=5)).isoformat()
    job_id = upload(staff_client, tmp_path, ["This is a plain public notice with nothing sensitive."])
    poll_job(staff_client, job_id, ["READY"])

    alerts = staff_client.get(f"/api/v1/notifications/recent?since={since}").json()["alerts"]
    assert all(a["job_id"] != job_id for a in alerts)


def test_recent_alerts_scoped_by_role(staff_client, admin_client, tmp_path):
    from datetime import datetime, timedelta

    since = (datetime.utcnow() - timedelta(seconds=5)).isoformat()
    job_id = upload(staff_client, tmp_path, ["NIC: 200012345678", "password: Sup3rSecret!2026"])
    poll_job(staff_client, job_id, ["AWAITING_DECISION"])

    admin_alerts = admin_client.get(f"/api/v1/notifications/recent?since={since}").json()["alerts"]
    assert any(a["job_id"] == job_id for a in admin_alerts)  # admin sees every user's alerts


def test_stream_endpoint_requires_auth(client):
    resp = client.get("/api/v1/notifications/stream")
    assert resp.status_code == 401
