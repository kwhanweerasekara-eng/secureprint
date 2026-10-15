from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.database.session import get_db
from apps.api.models.settings import SystemSetting
from apps.api.security.auth import require_admin

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])
settings = get_settings()

DEFAULT_WATERMARK = {"text": "RESTRICTED", "opacity": 0.10, "font_size": 26, "angle": 45}


class WatermarkConfig(BaseModel):
    text: str = "RESTRICTED"
    opacity: float = 0.10
    font_size: int = 26
    angle: float = 45


@router.get("/watermark", response_model=WatermarkConfig)
def get_watermark_config(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    row = db.get(SystemSetting, "watermark_config")
    return WatermarkConfig(**(row.value if row and row.value else DEFAULT_WATERMARK))


@router.patch("/watermark", response_model=WatermarkConfig)
def update_watermark_config(payload: WatermarkConfig, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    row = db.get(SystemSetting, "watermark_config")
    if row is None:
        row = SystemSetting(key="watermark_config", value=payload.model_dump(), description="Diagonal classification watermark")
        db.add(row)
    else:
        row.value = payload.model_dump()
    db.commit()
    return payload


@router.get("/health")
def system_health(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "app": settings.app_name,
        "environment": settings.environment,
        "database_ok": db_ok,
        "storage_incoming_writable": settings.incoming_dir.exists(),
        "storage_sanitized_writable": settings.sanitized_dir.exists(),
    }
