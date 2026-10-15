import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from apps.api.database.session import get_db
from apps.api.models.audit import AuditEvent
from apps.api.models.print_job import PrintJob
from apps.api.schemas.job import AuditEventOut
from apps.api.security.auth import require_admin

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


def _filtered_query(
    db: Session,
    date_from: datetime | None,
    date_to: datetime | None,
    user_id: str | None,
    classification: str | None,
    status_filter: str | None,
    event_type: str | None,
):
    q = db.query(AuditEvent)
    if date_from:
        q = q.filter(AuditEvent.created_at >= date_from)
    if date_to:
        q = q.filter(AuditEvent.created_at <= date_to)
    if user_id:
        q = q.filter(AuditEvent.user_id == user_id)
    if event_type:
        q = q.filter(AuditEvent.event_type == event_type)
    if classification or status_filter:
        q = q.join(PrintJob, PrintJob.id == AuditEvent.job_id)
        if classification:
            q = q.filter(PrintJob.classification == classification)
        if status_filter:
            q = q.filter(PrintJob.status == status_filter)
    return q.order_by(AuditEvent.created_at.desc())


@router.get("", response_model=list[AuditEventOut])
def list_audit_events(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    user_id: str | None = None,
    classification: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    event_type: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    q = _filtered_query(db, date_from, date_to, user_id, classification, status_filter, event_type)
    return q.limit(min(limit, 1000)).all()


@router.get("/export")
def export_audit_csv(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    user_id: str | None = None,
    classification: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    event_type: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    q = _filtered_query(db, date_from, date_to, user_id, classification, status_filter, event_type)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "created_at", "event_type", "job_id", "user_id", "message"])
    for e in q.limit(5000).all():
        writer.writerow([e.id, e.created_at.isoformat(), e.event_type.value if hasattr(e.event_type, "value") else e.event_type, e.job_id or "", e.user_id or "", e.message])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=secureprint_audit_export.csv"},
    )
