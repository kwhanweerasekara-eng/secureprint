from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from apps.api.database.session import get_db
from apps.api.models.audit import AuditEvent
from apps.api.models.detection import DetectionSummary
from apps.api.models.enums import Classification, JobAction, JobStatus, UserRole
from apps.api.models.print_job import PrintJob
from apps.api.models.user import User
from apps.api.schemas.dashboard import DashboardStats
from apps.api.security.auth import get_current_active_user

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

TERMINAL_STATUSES = (JobStatus.COMPLETED, JobStatus.READY, JobStatus.BLOCKED, JobStatus.CANCELLED, JobStatus.FAILED)


@router.get("/stats", response_model=DashboardStats)
def get_stats(db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    q = db.query(PrintJob)
    if user.role != UserRole.ADMIN:
        q = q.filter(PrintJob.user_id == user.id)

    jobs = q.all()
    total = len(jobs)

    classification_counts = {c.value: 0 for c in Classification}
    for j in jobs:
        if j.classification:
            classification_counts[j.classification.value] += 1

    blocked = sum(1 for j in jobs if j.status == JobStatus.BLOCKED or j.action == JobAction.BLOCKED)
    masked = sum(1 for j in jobs if j.action == JobAction.MASK_AND_PRINT)
    successful = sum(1 for j in jobs if j.status == JobStatus.COMPLETED)

    scored = [j.risk_score for j in jobs if j.risk_score is not None]
    avg_score = sum(scored) / len(scored) if scored else 0.0

    timed = [j.processing_time_ms for j in jobs if j.processing_time_ms is not None]
    avg_time = sum(timed) / len(timed) if timed else 0.0

    score_buckets = {"0-20": 0, "21-40": 0, "41-70": 0, "71-100": 0}
    for s in scored:
        if s <= 20:
            score_buckets["0-20"] += 1
        elif s <= 40:
            score_buckets["21-40"] += 1
        elif s <= 70:
            score_buckets["41-70"] += 1
        else:
            score_buckets["71-100"] += 1

    detections_q = db.query(DetectionSummary.category, func.sum(DetectionSummary.count))
    if user.role != UserRole.ADMIN:
        detections_q = detections_q.join(PrintJob, PrintJob.id == DetectionSummary.job_id).filter(PrintJob.user_id == user.id)
    detections_by_category: dict[str, int] = {cat: int(count) for cat, count in detections_q.group_by(DetectionSummary.category).all()}
    total_detections = sum(detections_by_category.values())

    top_categories = sorted(
        ({"category": k, "count": v} for k, v in detections_by_category.items()),
        key=lambda x: -x["count"],
    )[:10]

    since = datetime.utcnow() - timedelta(days=13)
    by_day: dict[str, int] = defaultdict(int)
    for j in jobs:
        if j.created_at >= since:
            by_day[j.created_at.strftime("%Y-%m-%d")] += 1
    jobs_over_time = [{"date": d, "count": by_day[d]} for d in sorted(by_day)]

    allowed = sum(1 for j in jobs if j.action in (JobAction.ALLOW_PRINT, JobAction.MASK_AND_PRINT))

    recent_jobs = [
        {
            "id": j.id,
            "filename": j.original_filename,
            "risk_score": j.risk_score,
            "classification": j.classification.value if j.classification else None,
            "status": j.status.value,
            "created_at": j.created_at.isoformat(),
        }
        for j in sorted(jobs, key=lambda j: j.created_at, reverse=True)[:10]
    ]

    events_q = db.query(AuditEvent)
    if user.role != UserRole.ADMIN:
        events_q = events_q.filter(AuditEvent.user_id == user.id)
    recent_events = [
        {
            "id": e.id,
            "job_id": e.job_id,
            "event_type": e.event_type.value if hasattr(e.event_type, "value") else e.event_type,
            "message": e.message,
            "created_at": e.created_at.isoformat(),
        }
        for e in events_q.order_by(AuditEvent.created_at.desc()).limit(12).all()
    ]

    return DashboardStats(
        documents_processed=total,
        public_count=classification_counts["PUBLIC"],
        internal_count=classification_counts["INTERNAL"],
        confidential_count=classification_counts["CONFIDENTIAL"],
        restricted_count=classification_counts["RESTRICTED"],
        sensitive_detections=total_detections,
        blocked_jobs=blocked,
        masked_jobs=masked,
        successful_jobs=successful,
        average_risk_score=round(avg_score, 1),
        average_processing_time_ms=round(avg_time, 1),
        classification_distribution=classification_counts,
        risk_score_distribution=score_buckets,
        detections_by_category=detections_by_category,
        jobs_over_time=jobs_over_time,
        blocked_vs_allowed={"allowed": allowed, "blocked": blocked},
        top_detected_categories=top_categories,
        recent_jobs=recent_jobs,
        recent_events=recent_events,
    )
