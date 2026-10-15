import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.base import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class DetectionSummary(Base):
    """Aggregate detection counts for a job. Raw sensitive values are never stored here."""

    __tablename__ = "detection_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    job_id: Mapped[str] = mapped_column(String(20), ForeignKey("print_jobs.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0)

    job = relationship("PrintJob", back_populates="detections")
