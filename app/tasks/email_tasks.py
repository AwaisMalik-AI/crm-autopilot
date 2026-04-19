"""Celery tasks: sequences, warmup, counters, daily reports."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.core.sync_db import sync_session_scope
from app.models.crm import EmailAccount, EmailSequence, EnrollmentStatus, SequenceEnrollment, SequenceStatus
from app.models.user import User
from app.services.email_engine import EmailEngine
from app.services.reporting import ReportingService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.email_tasks.process_pending_sequences")
def process_pending_sequences() -> dict[str, int]:
    now = datetime.now(timezone.utc)
    processed = 0
    errors = 0
    stmt = (
        select(SequenceEnrollment.id)
        .join(EmailSequence, SequenceEnrollment.sequence_id == EmailSequence.id)
        .where(
            SequenceEnrollment.status == EnrollmentStatus.ACTIVE,
            EmailSequence.status == SequenceStatus.ACTIVE,
            (SequenceEnrollment.next_send_at.is_(None)) | (SequenceEnrollment.next_send_at <= now),
        )
        .limit(200)
    )
    with sync_session_scope() as session:
        ids = list(session.execute(stmt).scalars().all())

    for eid in ids:
        try:
            with sync_session_scope() as session:
                result = EmailEngine().process_sequence_step(session, eid)
                if result.get("ok"):
                    processed += 1
        except Exception:
            logger.exception("sequence step failed enrollment_id=%s", eid)
            errors += 1
    return {"processed": processed, "errors": errors}


@celery_app.task(name="app.tasks.email_tasks.warmup_task")
def warmup_task() -> int:
    count = 0
    with sync_session_scope() as session:
        accounts = session.execute(select(EmailAccount).where(EmailAccount.is_active.is_(True))).scalars().all()
        engine = EmailEngine()
        for acc in accounts:
            engine.advance_warmup(session, acc)
            count += 1
    return count


@celery_app.task(name="app.tasks.email_tasks.counter_reset")
def counter_reset() -> None:
    with sync_session_scope() as session:
        session.execute(update(EmailAccount).values(sent_today=0))
    logger.info("Reset sent_today for all email accounts")


@celery_app.task(name="app.tasks.email_tasks.report_generation")
def report_generation() -> dict[str, int]:
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    n = 0
    with sync_session_scope() as session:
        users = session.execute(select(User).where(User.is_active.is_(True))).scalars().all()
        svc = ReportingService()
        for u in users:
            svc.generate_daily_report(session, u.id, yesterday)
            n += 1
    return {"reports_upserted": n, "report_date": str(yesterday)}
