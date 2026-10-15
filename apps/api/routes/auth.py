from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.database.session import get_db
from apps.api.models.audit import AuditEvent
from apps.api.models.enums import AuditEventType
from apps.api.models.user import User
from apps.api.schemas.auth import LoginRequest, UserOut
from apps.api.security.auth import create_access_token, get_current_active_user, verify_password
from apps.api.services.engine_loader import audit_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter((User.username == payload.username) | (User.email == payload.username))
        .first()
    )
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        if user:
            audit_service.record_event(
                db, AuditEvent, event_type=AuditEventType.LOGIN_FAILED.value, user_id=user.id, message="Invalid credentials"
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    token = create_access_token(user)
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )
    audit_service.record_event(db, AuditEvent, event_type=AuditEventType.LOGIN_SUCCESS.value, user_id=user.id)
    return user


@router.post("/logout")
def logout(response: Response, user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    response.delete_cookie(settings.cookie_name, path="/")
    audit_service.record_event(db, AuditEvent, event_type=AuditEventType.LOGOUT.value, user_id=user.id)
    return {"detail": "logged out"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_active_user)):
    return user
