"""Thin, storage-agnostic audit writer. The API layer injects the SQLAlchemy
session and model class so this engine module has no dependency on the web
application's ORM setup."""
from __future__ import annotations

from typing import Any


def record_event(
    db_session: Any,
    audit_event_model: Any,
    *,
    event_type: str,
    job_id: str | None = None,
    user_id: str | None = None,
    message: str = "",
    metadata: dict | None = None,
) -> Any:
    event = audit_event_model(
        job_id=job_id,
        user_id=user_id,
        event_type=event_type,
        message=message,
        event_metadata=metadata or {},
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event
