"""Password hashing, JWT session tokens, Personal Access Tokens, and RBAC
dependencies."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.database.session import get_db
from apps.api.models.api_token import ApiToken
from apps.api.models.enums import UserRole
from apps.api.models.user import User

_hasher = PasswordHasher()
settings = get_settings()

TOKEN_PREFIX = "sp_pat_"


def hash_password(raw_password: str) -> str:
    return _hasher.hash(raw_password)


def verify_password(raw_password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, raw_password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "role": user.role.value,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def generate_api_token() -> tuple[str, str, str]:
    """Returns (raw_token, token_hash, display_prefix). The raw token is
    shown to the user exactly once; only the hash is ever persisted."""
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    token_hash = hash_api_token(raw)
    display_prefix = raw[: len(TOKEN_PREFIX) + 6]
    return raw, token_hash, display_prefix


def hash_api_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _user_from_bearer_token(db: Session, raw_token: str) -> User | None:
    token_hash = hash_api_token(raw_token)
    record = db.query(ApiToken).filter(ApiToken.token_hash == token_hash, ApiToken.revoked == False).first()  # noqa: E712
    if not record:
        return None
    record.last_used_at = datetime.utcnow()
    db.commit()
    user = db.get(User, record.user_id)
    return user if user and user.is_active else None


def current_user_dependency():
    """Factory returning a FastAPI dependency that authenticates either the
    browser (HTTP-only session cookie) or an unattended client such as the
    Windows notification agent (`Authorization: Bearer <personal access
    token>`) - whichever is present."""

    def _dep(
        db: Session = Depends(get_db),
        cookie_value: str | None = Cookie(default=None, alias=settings.cookie_name),
        authorization: str | None = Header(default=None),
    ) -> User:
        if authorization and authorization.lower().startswith("bearer "):
            raw_token = authorization[7:].strip()
            user = _user_from_bearer_token(db, raw_token)
            if not user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked token")
            return user

        if not cookie_value:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        try:
            payload = decode_access_token(cookie_value)
        except jwt.PyJWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
        user = db.get(User, payload.get("sub"))
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        return user

    return _dep


get_current_active_user = current_user_dependency()


def require_admin(user: User = Depends(get_current_active_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return user
