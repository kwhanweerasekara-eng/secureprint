"""Real-time security alerts for the Windows notification agent (and anything
else that wants a push feed of "sensitive data identified" events).

"Sensitive data identified" is defined as exactly the set of events that
already interrupt a browser session for a decision, plus the fail-closed
outcomes - i.e. the same threshold used everywhere else in SecurePrint, not a
second one invented just for this feature:

  - AWAITING_DECISION  (CONFIDENTIAL/RESTRICTED - a human must choose)
  - BLOCKED            (policy denied printing, or a scanned/no-text document)
  - FAILED             (fail-closed: PDF/detection/redaction error)
  - REDACTION_VERIFICATION_FAILED (a sanitized PDF still contained a raw value)

The stream is implemented as Server-Sent Events: a one-way push is all a
notification agent needs, it rides over plain HTTPS through the existing
reverse proxy with no extra infrastructure, and it degrades to the REST
polling endpoint below with zero code changes on the client if the long-lived
connection ever gets dropped by a flaky network.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from apps.api.database.session import SessionLocal, get_db
from apps.api.models.audit import AuditEvent
from apps.api.models.detection import DetectionSummary
from apps.api.models.enums import UserRole
from apps.api.models.print_job import PrintJob
from apps.api.models.user import User
from apps.api.security.auth import get_current_active_user

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])

ALERT_EVENT_TYPES = ["AWAITING_DECISION", "BLOCKED", "FAILED", "REDACTION_VERIFICATION_FAILED"]
POLL_INTERVAL_SECONDS = 2.0


def _serialize_alert(db: Session, event: AuditEvent) -> dict:
    job = db.get(PrintJob, event.job_id) if event.job_id else None
    categories: dict[str, int] = {}
    if job:
        for row in db.query(DetectionSummary).filter(DetectionSummary.job_id == job.id).all():
            categories[row.category] = row.count
    return {
        "id": event.id,
        "event_type": event.event_type.value if hasattr(event.event_type, "value") else event.event_type,
        "message": event.message,
        "created_at": event.created_at.isoformat(),
        "job_id": event.job_id,
        "filename": job.original_filename if job else None,
        "risk_score": job.risk_score if job else None,
        "classification": job.classification.value if job and job.classification else None,
        "status": job.status.value if job else None,
        "categories": categories,
    }


def _fetch_alerts_since(db: Session, user: User, since: datetime) -> list[dict]:
    q = db.query(AuditEvent).filter(AuditEvent.event_type.in_(ALERT_EVENT_TYPES), AuditEvent.created_at > since)
    if user.role != UserRole.ADMIN:
        q = q.join(PrintJob, PrintJob.id == AuditEvent.job_id).filter(PrintJob.user_id == user.id)
    events = q.order_by(AuditEvent.created_at).all()
    return [_serialize_alert(db, e) for e in events]


@router.get("/recent")
def recent_alerts(since: datetime | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """Polling fallback for the agent: returns every alert-worthy event after
    `since` (defaults to the last hour). The agent's own reconnect logic uses
    this to catch up on anything missed while the SSE stream was down."""
    cutoff = since or (datetime.utcnow().replace(microsecond=0))
    return {"server_time": datetime.utcnow().isoformat(), "alerts": _fetch_alerts_since(db, user, cutoff)}


@router.get("/stream")
async def stream_alerts(request: Request, user: User = Depends(get_current_active_user)):
    async def event_generator():
        last_check = datetime.utcnow()
        yield "event: connected\ndata: {}\n\n"

        while True:
            if await request.is_disconnected():
                break

            db = SessionLocal()
            try:
                alerts = _fetch_alerts_since(db, user, last_check)
                last_check = datetime.utcnow()
            finally:
                db.close()

            for alert in alerts:
                yield f"event: alert\ndata: {json.dumps(alert)}\n\n"

            yield ": keep-alive\n\n"
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
