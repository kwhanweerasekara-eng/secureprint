from datetime import datetime

from pydantic import BaseModel


class DetectionSummaryOut(BaseModel):
    category: str
    count: int

    model_config = {"from_attributes": True}


class AuditEventOut(BaseModel):
    id: str
    job_id: str | None = None
    user_id: str | None = None
    event_type: str
    message: str
    event_metadata: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: str
    original_filename: str
    status: str
    action: str
    block_reason: str
    status_message: str
    risk_score: int | None
    classification: str | None
    page_count: int
    has_text_layer: bool
    processing_time_ms: int | None
    printer_id: str | None
    created_at: datetime
    updated_at: datetime
    user_id: str

    model_config = {"from_attributes": True}


class JobDetailOut(JobOut):
    detections: list[DetectionSummaryOut] = []
    events: list[AuditEventOut] = []
