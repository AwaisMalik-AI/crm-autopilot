"""Celery tasks for smart lists."""

import logging

from sqlalchemy import select

from app.core.sync_db import sync_session_scope
from app.models.crm import SmartList
from app.services.smart_list_engine import SmartListEngine
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.list_tasks.refresh_all_smart_lists")
def refresh_all_smart_lists() -> dict[str, int]:
    count = 0
    with sync_session_scope() as session:
        rows = session.execute(select(SmartList).where(SmartList.is_dynamic.is_(True))).scalars().all()
        engine = SmartListEngine()
        for sl in rows:
            try:
                engine.refresh(session, sl)
                count += 1
            except Exception:
                logger.exception("smart list refresh failed id=%s", sl.id)
    return {"refreshed": count}
