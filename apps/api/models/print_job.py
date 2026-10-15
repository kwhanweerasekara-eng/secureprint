import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.base import Base
from apps.api.models.enums import BlockReason, Classification, JobAction, JobStatus


def gen_job_id() -> str:
    return f"SP-{uuid.uuid4().hex[:8].upper()}"


class PrintJob(Base):
    __tablename__ = "print_jobs"

    id: Mapped[str] = mapped_column(String(20), primary_key=True, default=gen_job_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    has_text_layer: Mapped[bool] = mapped_column(Boolean, default=True)

    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.UPLOADED, nullable=False)
    action: Mapped[JobAction] = mapped_column(Enum(JobAction), default=JobAction.PENDING)
    block_reason: Mapped[BlockReason] = mapped_column(Enum(BlockReason), default=BlockReason.NONE)
    status_message: Mapped[str] = mapped_column(String(500), default="")

    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    classification: Mapped[Classification | None] = mapped_column(Enum(Classification), nullable=True)

    original_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sanitized_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    printer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("printers.id"), nullable=True)

    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    decided_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="print_jobs")
    printer = relationship("Printer", back_populates="print_jobs")
    detections = relationship("DetectionSummary", back_populates="job", cascade="all, delete-orphan")
    audit_events = relationship("AuditEvent", back_populates="job", cascade="all, delete-orphan")
