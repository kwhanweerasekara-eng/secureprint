"""Central application configuration for the SecurePrint API."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/config.py -> apps/api -> apps -> <repo root>
API_DIR = Path(__file__).resolve().parent
APPS_DIR = API_DIR.parent
REPO_ROOT = APPS_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(REPO_ROOT / ".env"), extra="ignore")

    app_name: str = "SecurePrint"
    organisation_name: str = "SecurePrint Demo Org"
    environment: str = "development"

    database_url: str = f"sqlite:///{REPO_ROOT / 'storage' / 'secureprint.db'}"

    jwt_secret: str = "CHANGE_ME_DEV_SECRET_DO_NOT_USE_IN_PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 8
    cookie_name: str = "secureprint_session"
    cookie_secure: bool = False  # set True behind HTTPS in production

    cors_origins: list[str] = ["http://localhost:3000"]

    storage_root: Path = REPO_ROOT / "storage"
    config_dir: Path = REPO_ROOT / "config"

    max_upload_mb: int = 25

    sanitized_retention_days: int = 30

    # Seed account passwords - override via env vars for any non-local deployment.
    default_admin_password: str = "admin123"
    default_staff_password: str = "staff123"

    @property
    def incoming_dir(self) -> Path:
        return self.storage_root / "incoming"

    @property
    def processing_dir(self) -> Path:
        return self.storage_root / "processing"

    @property
    def sanitized_dir(self) -> Path:
        return self.storage_root / "sanitized"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    for d in (settings.incoming_dir, settings.processing_dir, settings.sanitized_dir):
        d.mkdir(parents=True, exist_ok=True)
    return settings
