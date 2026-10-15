from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.database.session import get_db
from apps.api.models.audit import AuditEvent
from apps.api.models.enums import AuditEventType, JobStatus, PrinterStatus, UserRole
from apps.api.models.print_job import PrintJob
from apps.api.models.printer import Printer
from apps.api.models.user import User
from apps.api.schemas.job import AuditEventOut, DetectionSummaryOut, JobDetailOut, JobOut
from apps.api.security.auth import get_current_active_user
from apps.api.services import printing
from apps.api.services.engine_loader import audit_service
from apps.api.services.pipeline import approve_mask_and_continue, cancel_job

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def _scope_query(db: Session, user: User):
    q = db.query(PrintJob)
    if user.role != UserRole.ADMIN:
        q = q.filter(PrintJob.user_id == user.id)
    return q


def _get_owned_job(db: Session, user: User, job_id: str) -> PrintJob:
    job = db.get(PrintJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if user.role != UserRole.ADMIN and job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this job")
    return job


@router.get("", response_model=list[JobOut])
def list_jobs(
    status_filter: str | None = None,
    classification: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    q = _scope_query(db, user)
    if status_filter:
        q = q.filter(PrintJob.status == status_filter)
    if classification:
        q = q.filter(PrintJob.classification == classification)
    return q.order_by(PrintJob.created_at.desc()).limit(min(limit, 500)).all()


@router.get("/{job_id}", response_model=JobDetailOut)
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    job = _get_owned_job(db, user, job_id)
    detections = [DetectionSummaryOut.model_validate(d) for d in job.detections]
    events = [
        AuditEventOut.model_validate(e)
        for e in sorted(job.audit_events, key=lambda e: e.created_at)
    ]
    out = JobDetailOut.model_validate(job)
    out.detections = detections
    out.events = events
    return out


@router.post("/{job_id}/sanitize", response_model=JobOut)
def sanitize(job_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    job = _get_owned_job(db, user, job_id)
    if job.status != JobStatus.AWAITING_DECISION:
        raise HTTPException(status_code=409, detail=f"Job is not awaiting a decision (status={job.status.value})")
    background_tasks.add_task(approve_mask_and_continue, job_id, user.id)
    db.refresh(job)
    return job


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    job = _get_owned_job(db, user, job_id)
    if job.status in (JobStatus.CANCELLED, JobStatus.COMPLETED, JobStatus.BLOCKED):
        raise HTTPException(status_code=409, detail=f"Job cannot be cancelled (status={job.status.value})")
    cancel_job(job_id, user.id)
    db.refresh(job)
    return job


@router.get("/{job_id}/document")
def get_document(
    job_id: str, download: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)
):
    job = _get_owned_job(db, user, job_id)
    if job.status not in (JobStatus.READY, JobStatus.PRINTING, JobStatus.COMPLETED):
        raise HTTPException(status_code=409, detail="Sanitized document is not ready yet")
    if not job.sanitized_path or not Path(job.sanitized_path).exists():
        raise HTTPException(status_code=404, detail="Sanitized document not found")
    return FileResponse(
        job.sanitized_path,
        media_type="application/pdf",
        filename=f"{job_id}_sanitized.pdf",
        # Cross-origin <a download> is ignored by browsers, so the frontend
        # drives this via ?download=1 instead of relying on the HTML attribute.
        content_disposition_type="attachment" if download else "inline",
    )


class PrintRequest(BaseModel):
    printer_id: str | None = None
    # Print dialog settings, passed on to a server printer.
    copies: int = Field(1, ge=1, le=99)
    sides: Literal["one-sided", "two-sided-long-edge", "two-sided-short-edge"] | None = None
    # Set by the print capture when it releases the job itself, e.g. "local printer 'Office_HP'".
    released_to: str | None = Field(None, max_length=120)


@router.post("/{job_id}/print", response_model=JobOut)
def print_job(job_id: str, payload: PrintRequest = PrintRequest(), db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    job = _get_owned_job(db, user, job_id)
    if job.status != JobStatus.READY:
        raise HTTPException(status_code=409, detail=f"Job is not ready to print (status={job.status.value})")
    if not job.sanitized_path or not Path(job.sanitized_path).exists():
        raise HTTPException(status_code=404, detail="Sanitized document not found")

    printer = None
    if payload.printer_id:
        printer = db.get(Printer, payload.printer_id)
        if not printer:
            raise HTTPException(status_code=404, detail="Printer not found")

    job.status = JobStatus.PRINTING
    job.printer_id = printer.id if printer else None
    db.commit()

    options = printing.PrintOptions(copies=payload.copies, sides=payload.sides)
    settings = {"copies": options.copies, "sides": options.sides or "printer default"}
    if printer is None:
        # Web Analysis Mode: the browser's native print dialog handles real
        # printer delivery on the user's own machine - nothing left to do here.
        # The print capture also lands here when it prints or saves the job itself.
        if payload.released_to:
            message = f"Sanitized document released by the SecurePrint print capture to {payload.released_to}{options.describe()}"
        else:
            message = "Sanitized document released to the browser for printing (Web Analysis Mode)"
        audit_service.record_event(
            db, AuditEvent, event_type=AuditEventType.RELEASED_TO_PRINTER.value, job_id=job.id, user_id=user.id,
            message=message, metadata=settings,
        )
        job.status = JobStatus.COMPLETED
        db.commit()
        audit_service.record_event(db, AuditEvent, event_type=AuditEventType.PRINT_COMPLETED.value, job_id=job.id, user_id=user.id)
        return job

    # Managed mode: the backend delivers the sanitized PDF directly to the
    # network printer over IPP/AppSocket. Fail closed - a delivery failure
    # leaves the job in READY (never COMPLETED) so it can be retried.
    pdf_bytes = Path(job.sanitized_path).read_bytes()
    try:
        printing.print_to_printer(
            printer.protocol.value, printer.host, printer.port, printer.ipp_path, printer.use_tls, pdf_bytes, job.id,
            options=options,
        )
    except printing.PrintDeliveryError as exc:
        job.status = JobStatus.READY
        printer.status = PrinterStatus.OFFLINE
        db.commit()
        audit_service.record_event(
            db, AuditEvent, event_type=AuditEventType.PRINT_FAILED.value, job_id=job.id, user_id=user.id,
            message=f"Delivery to printer '{printer.name}' failed: {exc}",
        )
        raise HTTPException(status_code=502, detail=f"Could not deliver document to printer: {exc}")

    printer.status = PrinterStatus.ONLINE
    audit_service.record_event(
        db, AuditEvent, event_type=AuditEventType.RELEASED_TO_PRINTER.value, job_id=job.id, user_id=user.id,
        message=f"Sanitized document sent directly to network printer '{printer.name}' ({printer.protocol.value}){options.describe()}",
        metadata=settings,
    )
    job.status = JobStatus.COMPLETED
    db.commit()
    audit_service.record_event(db, AuditEvent, event_type=AuditEventType.PRINT_COMPLETED.value, job_id=job.id, user_id=user.id)
    return job
