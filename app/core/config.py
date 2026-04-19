"""Application settings loaded from environment (no secrets in code)."""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "CRM Autopilot"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api"

    DATABASE_URL: str = Field(
        ...,
        description="SQLAlchemy URL, e.g. postgresql+asyncpg://user:pass@host:5432/db",
    )
    REDIS_URL: str = Field(..., description="Redis URL for Celery and caching")

    SECRET_KEY: str = Field(..., min_length=32, description="Signing key for JWT and encryption derivation")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    LLM_API_URL: str | None = None
    LLM_API_KEY: str | None = None
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TIMEOUT_SECONDS: float = 45.0

    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None

    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = True

    EMAIL_DAILY_LIMIT: int = 50
    WARMUP_ENABLED: bool = True

    WEBHOOK_SECRET: str = Field(..., min_length=16, description="HMAC secret for inbound webhooks")

    IDEAL_TITLE_KEYWORDS: str = Field(
        default="founder,ceo,cto,director,head,vp,owner",
        description="Comma-separated keywords for title match boost",
    )
    IDEAL_COMPANY_KEYWORDS: str = Field(
        default="saas,software,agency,consulting,tech",
        description="Comma-separated keywords for company match boost",
    )

    @model_validator(mode="after")
    def celery_defaults_from_redis(self):
        if not self.CELERY_BROKER_URL:
            object.__setattr__(self, "CELERY_BROKER_URL", self.REDIS_URL)
        if not self.CELERY_RESULT_BACKEND:
            object.__setattr__(self, "CELERY_RESULT_BACKEND", self.REDIS_URL)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
