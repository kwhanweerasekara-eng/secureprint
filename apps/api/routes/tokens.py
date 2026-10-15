"""Personal Access Tokens - lets an unattended client (the Windows
notification agent) authenticate as a specific user without ever holding
that user's password. Every user manages their own tokens; there is no
cross-user administration of tokens (matches the "personal" access token
convention used by GitHub, GitLab, etc.)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.database.session import get_db
from apps.api.models.api_token import ApiToken
from apps.api.models.audit import AuditEvent
from apps.api.models.enums import AuditEventType
from apps.api.models.user import User
from apps.api.schemas.token import ApiTokenCreate, ApiTokenCreated, ApiTokenOut
from apps.api.security.auth import generate_api_token, get_current_active_user
from apps.api.services.engine_loader import audit_service

router = APIRouter(prefix="/api/v1/tokens", tags=["tokens"])


@router.get("", response_model=list[ApiTokenOut])
def list_tokens(db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    return db.query(ApiToken).filter(ApiToken.user_id == user.id).order_by(ApiToken.created_at.desc()).all()


@router.post("", response_model=ApiTokenCreated, status_code=201)
def create_token(payload: ApiTokenCreate, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    raw_token, token_hash, prefix = generate_api_token()
    record = ApiToken(user_id=user.id, name=payload.name, token_hash=token_hash, token_prefix=prefix)
    db.add(record)
    db.commit()
    db.refresh(record)

    audit_service.record_event(
        db, AuditEvent, event_type=AuditEventType.TOKEN_CREATED.value, user_id=user.id,
        message=f"Personal access token '{payload.name}' created",
    )

    return ApiTokenCreated(id=record.id, name=record.name, token=raw_token, token_prefix=record.token_prefix, created_at=record.created_at)


@router.delete("/{token_id}", status_code=204)
def revoke_token(token_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    record = db.get(ApiToken, token_id)
    if not record or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="Token not found")
    db.delete(record)
    db.commit()
    audit_service.record_event(
        db, AuditEvent, event_type=AuditEventType.TOKEN_REVOKED.value, user_id=user.id,
        message=f"Personal access token '{record.name}' revoked",
    )
