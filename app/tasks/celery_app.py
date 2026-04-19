"""Celery application and beat schedule."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "crm_autopilot",
    broker=str(settings.CELERY_BROKER_URL),
    backend=str(settings.CELERY_RESULT_BACKEND),
    include=["app.tasks.email_tasks", "app.tasks.list_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "process_sequence_queue": {
        "task": "app.tasks.email_tasks.process_pending_sequences",
        "schedule": crontab(minute="*/15"),
    },
    "warmup_advance": {
        "task": "app.tasks.email_tasks.warmup_task",
        "schedule": crontab(hour=1, minute=0),
    },
    "reset_daily_counters": {
        "task": "app.tasks.email_tasks.counter_reset",
        "schedule": crontab(hour=0, minute=0),
    },
    "refresh_smart_lists": {
        "task": "app.tasks.list_tasks.refresh_all_smart_lists",
        "schedule": crontab(hour=3, minute=0),
    },
    "generate_daily_reports": {
        "task": "app.tasks.email_tasks.report_generation",
        "schedule": crontab(hour=6, minute=0),
    },
}
