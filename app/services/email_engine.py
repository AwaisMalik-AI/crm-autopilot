"""SMTP send, sequence steps, and mailbox warmup."""

from __future__ import annotations

import logging
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.models.crm import (
    Contact,
    EmailAccount,
    EmailEvent,
    EmailEventStatus,
    EmailSequence,
    EnrollmentStatus,
    Lead,
    LeadActivity,
    LeadActivityType,
    PipelineStage,
    SequenceEnrollment,
    SequenceStatus,
)
from app.services.template_render import render_template

logger = logging.getLogger(__name__)


class EmailEngine:
    def send_email(
        self,
        session: Session,
        account: EmailAccount,
        to: str,
        subject: str,
        body: str,
        *,
        tracking_id: str | None = None,
        enrollment_id: int | None = None,
    ) -> EmailEvent:
        settings = get_settings()
        pwd = decrypt_secret(account.smtp_password_encrypted)
        message_id = tracking_id or f"<{uuid.uuid4()}@{account.smtp_host}>"

        event = EmailEvent(
            enrollment_id=enrollment_id,
            email_account_id=account.id,
            to_email=to,
            subject=subject,
            status=EmailEventStatus.QUEUED,
            message_id=message_id,
        )
        session.add(event)
        session.flush()

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = account.email
        msg["To"] = to
        msg["Message-ID"] = message_id
        msg.set_content(body)

        try:
            if account.smtp_port == 465:
                with smtplib.SMTP_SSL(account.smtp_host, account.smtp_port, timeout=60) as smtp:
                    smtp.login(account.smtp_user, pwd)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=60) as smtp:
                    if settings.SMTP_USE_TLS:
                        smtp.starttls()
                    smtp.login(account.smtp_user, pwd)
                    smtp.send_message(msg)
            event.status = EmailEventStatus.SENT
            account.sent_today = (account.sent_today or 0) + 1
        except Exception as exc:
            logger.exception("SMTP send failed: %s", exc)
            event.status = EmailEventStatus.FAILED
            raise

        session.flush()
        return event

    def check_warmup_eligibility(self, account: EmailAccount) -> bool:
        settings = get_settings()
        if not settings.WARMUP_ENABLED:
            return account.sent_today < account.daily_limit
        cap = min(account.daily_limit, max(account.warmup_max_per_day, account.warmup_stage * 3 + 5))
        return account.sent_today < cap

    def advance_warmup(self, session: Session, account: EmailAccount) -> EmailAccount:
        settings = get_settings()
        if not settings.WARMUP_ENABLED:
            return account
        account.warmup_stage = min(50, account.warmup_stage + 1)
        account.warmup_max_per_day = min(account.daily_limit, account.warmup_max_per_day + 5)
        session.add(account)
        session.flush()
        return account

    def process_sequence_step(self, session: Session, enrollment_id: int) -> dict[str, Any]:
        enr = session.get(SequenceEnrollment, enrollment_id)
        if not enr or enr.status != EnrollmentStatus.ACTIVE:
            return {"ok": False, "reason": "inactive_or_missing"}

        seq = session.get(EmailSequence, enr.sequence_id)
        if not seq or seq.status != SequenceStatus.ACTIVE:
            return {"ok": False, "reason": "sequence_not_active"}

        steps = sorted(seq.steps or [], key=lambda s: int(s.get("step_number", 0)))
        if not steps:
            return {"ok": False, "reason": "no_steps"}

        next_idx = enr.current_step
        if next_idx >= len(steps):
            enr.status = EnrollmentStatus.COMPLETED
            enr.completed_at = datetime.now(timezone.utc)
            session.add(enr)
            session.flush()
            return {"ok": True, "completed": True}

        step = steps[next_idx]
        contact = session.get(Contact, enr.contact_id)
        if not contact:
            return {"ok": False, "reason": "contact_missing"}

        stmt = (
            select(EmailAccount)
            .where(EmailAccount.user_id == seq.created_by_id, EmailAccount.is_active.is_(True))
            .order_by(EmailAccount.id)
        )
        account = session.execute(stmt).scalars().first()
        if not account:
            return {"ok": False, "reason": "no_email_account"}

        if not self.check_warmup_eligibility(account):
            return {"ok": False, "reason": "warmup_or_limit"}

        subject = render_template(step.get("subject_template", ""), contact)
        body = render_template(step.get("body_template", ""), contact)

        self.send_email(
            session,
            account,
            contact.email,
            subject,
            body,
            enrollment_id=enr.id,
        )

        lead_id = self._ensure_lead(session, contact, seq.created_by_id)
        act = LeadActivity(
            lead_id=lead_id,
            activity_type=LeadActivityType.EMAIL_SENT,
            description=f"Sequence '{seq.name}' step {step.get('step_number', next_idx + 1)}",
            metadata_={"enrollment_id": enr.id, "sequence_id": seq.id},
            created_by_id=seq.created_by_id,
        )
        session.add(act)

        delay_h = float(step.get("delay_hours", 24))
        enr.current_step = next_idx + 1
        if enr.current_step >= len(steps):
            enr.status = EnrollmentStatus.COMPLETED
            enr.completed_at = datetime.now(timezone.utc)
            enr.next_send_at = None
        else:
            enr.next_send_at = datetime.now(timezone.utc) + timedelta(hours=delay_h)
        session.add(enr)
        session.flush()
        return {"ok": True, "sent_step": next_idx + 1}

    def _ensure_lead(self, session: Session, contact: Contact, user_id: int) -> int:
        stmt = select(Lead).where(Lead.contact_id == contact.id).limit(1)
        lead = session.execute(stmt).scalar_one_or_none()
        if lead:
            return lead.id
        lead = Lead(
            contact_id=contact.id,
            pipeline_stage=PipelineStage.NEW,
            source="sequence",
            assigned_to_id=user_id,
        )
        session.add(lead)
        session.flush()
        return lead.id
