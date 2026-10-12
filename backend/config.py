"""Environment-driven configuration. All secrets come from .env / the environment."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DEV_SECRET = "dev-only-change-me"


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _database_url() -> str:
    """Accept the plain postgres:// URLs that Render/Railway/Heroku provide."""
    url = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{ROOT_DIR / 'data' / 'aura.db'}")
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


@dataclass(frozen=True)
class Settings:
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = _env_bool("DEBUG", False)
    DATABASE_URL: str = _database_url()
    SECRET_KEY: str = os.getenv("SECRET_KEY", DEV_SECRET)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))
    REQUIRE_AUTH: bool = _env_bool("REQUIRE_AUTH", False)
    DEMO_ADMIN_USER: str = os.getenv("DEMO_ADMIN_USER", "admin")
    DEMO_ADMIN_PASSWORD: str = os.getenv("DEMO_ADMIN_PASSWORD", "ChangeMe-Aura-2026")
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")
    RATE_LIMIT_PREDICT_PER_MIN: int = int(os.getenv("RATE_LIMIT_PREDICT_PER_MIN", "60"))
    ARTIFACT_DIR: Path = ROOT_DIR / "ml" / "artifacts"
    FRONTEND_DIR: Path = ROOT_DIR / "frontend"
    # --- ROI assumptions (editable business inputs, returned by /api/metrics/roi) ---
    DOWNTIME_COST_PER_HOUR_USD: float = float(os.getenv("DOWNTIME_COST_PER_HOUR_USD", "12400"))
    AVG_DOWNTIME_HOURS_PER_FAILURE: float = float(os.getenv("AVG_DOWNTIME_HOURS_PER_FAILURE", "8"))
    SCHEDULED_HOURS_PER_MONTH: float = float(os.getenv("SCHEDULED_HOURS_PER_MONTH", "720"))
    UNPLANNED_REPAIR_COST_USD: float = float(os.getenv("UNPLANNED_REPAIR_COST_USD", "15000"))
    PLANNED_REPAIR_COST_USD: float = float(os.getenv("PLANNED_REPAIR_COST_USD", "4000"))


settings = Settings()

if settings.ENVIRONMENT == "production" and settings.SECRET_KEY == DEV_SECRET:
    raise RuntimeError("SECRET_KEY must be set to a strong random value in production.")
