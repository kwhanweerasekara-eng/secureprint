from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from apps.api.database.session import get_db
from apps.api.models.audit import AuditEvent
from apps.api.models.enums import AuditEventType, JobStatus
from apps.api.models.print_job import PrintJob
from apps.api.models.user import User
from apps.api.schemas.job import JobOut
from apps.api.security.auth import get_current_active_user
from apps.api.services.engine_loader import audit_service
from apps.api.services.pipeline import run_analysis_pipeline
from apps.api.services.storage import UploadValidationError, save_upload

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

# Where a job entered the system. "web" is a manual upload on the Analyze page;
# "virtual_printer" is a job captured by a print capture agent from the
# SecurePrint printer. Recorded in the audit trail so evaluation can separate the two.
JOB_SOURCES = {"web", "virtual_printer"}


@router.post("/analyze", response_model=JobOut, status_code=202)
async def analyze_document(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    source: str = "web",
    # Sent by the print capture: the Print dialog's copies, and the computer
    # account and host the job was printed from.
    copies: int = Query(1, ge=1, le=99),
    print_user: str = Query("", max_length=64),
    client_host: str = Query("", max_length=128),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    if source not in JOB_SOURCES:
        raise HTTPException(status_code=400, detail=f"Unknown job source: {source}")
    try:
        stored_path, display_filename, sha256_hex, _size = await save_upload(file)
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    job = PrintJob(
        user_id=user.id,
        original_filename=display_filename,
        sha256=sha256_hex,
        original_path=str(stored_path),
        status=JobStatus.UPLOADED,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    audit_service.record_event(
        db,
        AuditEvent,
        event_type=AuditEventType.JOB_RECEIVED.value,
        job_id=job.id,
        user_id=user.id,
        message=f"Received {display_filename}" + (_printer_origin(print_user, client_host, copies) if source == "virtual_printer" else ""),
        metadata={"source": source, "copies": copies, "print_user": print_user, "client_host": client_host},
    )

    background_tasks.add_task(run_analysis_pipeline, job.id)
    return job


def _printer_origin(print_user: str, client_host: str, copies: int) -> str:
    """ "from the SecurePrint virtual printer (printed by vinu on vinus-mac, 3 copies)" """
    details = []
    if print_user:
        details.append(f"printed by {print_user}" + (f" on {client_host}" if client_host and client_host != "localhost" else ""))
    if copies > 1:
        details.append(f"{copies} copies")
    return " from the SecurePrint virtual printer" + (f" ({', '.join(details)})" if details else "")
