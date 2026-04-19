"""Synchronous SQLAlchemy for Celery workers (no asyncio event loop)."""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _to_sync_url(url: str) -> str:
    u = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    u = u.replace("sqlite+aiosqlite://", "sqlite://", 1)
    if u.startswith("postgres://"):
        u = "postgresql+psycopg2://" + u[len("postgres://") :]
    return u


_settings = get_settings()
sync_engine = create_engine(
    _to_sync_url(str(_settings.DATABASE_URL)),
    echo=_settings.DEBUG,
    pool_pre_ping=True,
)
SyncSessionLocal = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False, expire_on_commit=False)


@contextmanager
def sync_session_scope() -> Generator[Session, None, None]:
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
