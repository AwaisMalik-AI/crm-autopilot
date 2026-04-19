"""Analytics aggregates for pipeline, email, sequences, and daily reports."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.crm import (
    DailyReport,
    EmailAccount,
    EmailEvent,
    EmailEventStatus,
    EmailSequence,
    Lead,
    LeadActivity,
    LeadActivityType,
    PipelineStage,
    SequenceEnrollment,
)


class ReportingService:
    def generate_daily_report(self, session: Session, user_id: int, report_date: date) -> DailyReport:
        start = datetime.combine(report_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end = start + timedelta(days=1)

        sent = session.scalar(
            select(func.count())
            .select_from(EmailEvent)
            .join(EmailAccount, EmailEvent.email_account_id == EmailAccount.id)
            .where(
                EmailEvent.created_at >= start,
                EmailEvent.created_at < end,
                EmailEvent.status == EmailEventStatus.SENT,
                EmailAccount.user_id == user_id,
            )
        ) or 0

        opened = session.scalar(
            select(func.count())
            .select_from(EmailEvent)
            .join(EmailAccount, EmailEvent.email_account_id == EmailAccount.id)
            .where(
                EmailEvent.opened_at.isnot(None),
                EmailEvent.opened_at >= start,
                EmailEvent.opened_at < end,
                EmailAccount.user_id == user_id,
            )
        ) or 0

        replies = session.scalar(
            select(func.count())
            .select_from(EmailEvent)
            .join(EmailAccount, EmailEvent.email_account_id == EmailAccount.id)
            .where(
                EmailEvent.replied_at.isnot(None),
                EmailEvent.replied_at >= start,
                EmailEvent.replied_at < end,
                EmailAccount.user_id == user_id,
            )
        ) or 0

        new_leads = session.scalar(
            select(func.count())
            .select_from(Lead)
            .where(
                Lead.created_at >= start,
                Lead.created_at < end,
                Lead.assigned_to_id == user_id,
            )
        ) or 0

        moved = session.scalar(
            select(func.count())
            .select_from(LeadActivity)
            .join(Lead, LeadActivity.lead_id == Lead.id)
            .where(
                LeadActivity.activity_type == LeadActivityType.STAGE_CHANGE,
                LeadActivity.created_at >= start,
                LeadActivity.created_at < end,
                Lead.assigned_to_id == user_id,
            )
        ) or 0

        summary = (
            f"Sent {sent} emails, {opened} opens, {replies} replies. "
            f"New leads {new_leads}, stage changes logged {moved}."
        )

        existing = session.execute(
            select(DailyReport).where(DailyReport.user_id == user_id, DailyReport.report_date == report_date)
        ).scalar_one_or_none()
        if existing:
            existing.emails_sent = int(sent)
            existing.emails_opened = int(opened)
            existing.replies_received = int(replies)
            existing.new_leads = int(new_leads)
            existing.leads_moved = int(moved)
            existing.summary_text = summary
            session.add(existing)
            session.flush()
            return existing

        row = DailyReport(
            user_id=user_id,
            report_date=report_date,
            emails_sent=int(sent),
            emails_opened=int(opened),
            replies_received=int(replies),
            new_leads=int(new_leads),
            leads_moved=int(moved),
            summary_text=summary,
        )
        session.add(row)
        session.flush()
        return row

    def get_pipeline_summary(self, session: Session, user_id: int | None = None) -> dict[str, Any]:
        q = select(Lead.pipeline_stage, func.count()).group_by(Lead.pipeline_stage)
        if user_id is not None:
            q = q.where(Lead.assigned_to_id == user_id)
        rows = session.execute(q).all()
        stages: list[dict[str, Any]] = []
        total = 0
        counts: dict[str, int] = {}
        for stage, cnt in rows:
            key = stage.value if hasattr(stage, "value") else str(stage)
            counts[key] = int(cnt)
            total += int(cnt)
            stages.append({"stage": key, "count": int(cnt)})

        order = [s.value for s in PipelineStage]
        stages.sort(key=lambda x: order.index(x["stage"]) if x["stage"] in order else 99)

        conversion_rates: dict[str, float] = {}
        won = counts.get(PipelineStage.WON.value, 0)
        lost = counts.get(PipelineStage.LOST.value, 0)
        denom = max(1, won + lost)
        conversion_rates["win_rate_closed"] = round(won / denom, 4)
        conversion_rates["total_leads"] = float(total)
        return {"stages": stages, "conversion_rates": conversion_rates}

    def get_sequence_performance(self, session: Session, sequence_id: int) -> dict[str, Any]:
        seq = session.get(EmailSequence, sequence_id)
        if not seq:
            return {}

        stmt = (
            select(EmailEvent)
            .join(SequenceEnrollment, EmailEvent.enrollment_id == SequenceEnrollment.id)
            .where(SequenceEnrollment.sequence_id == sequence_id)
        )
        seq_events = session.execute(stmt).scalars().all()

        opened = sum(1 for e in seq_events if e.opened_at)
        replied = sum(1 for e in seq_events if e.replied_at)
        bounced = sum(1 for e in seq_events if e.status == EmailEventStatus.BOUNCED or e.bounced_at)

        enrolled = max(seq.total_enrolled, 1)
        open_rate = round(opened / enrolled, 4)
        reply_rate = round(replied / enrolled, 4)
        bounce_rate = round(bounced / enrolled, 4)

        per_step_map: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for e in seq_events:
            step_guess = 0
            if e.enrollment:
                step_guess = max(0, e.enrollment.current_step - 1)
            per_step_map[step_guess]["sent"] += 1
            if e.opened_at:
                per_step_map[step_guess]["opened"] += 1
            if e.replied_at:
                per_step_map[step_guess]["replied"] += 1

        per_step: list[dict[str, Any]] = []
        for step_num in sorted(per_step_map.keys()):
            bucket = per_step_map[step_num]
            s = max(bucket["sent"], 1)
            per_step.append(
                {
                    "step": step_num + 1,
                    "sent": bucket["sent"],
                    "open_rate": round(bucket["opened"] / s, 4),
                    "reply_rate": round(bucket["replied"] / s, 4),
                }
            )

        return {
            "sequence_id": sequence_id,
            "total_enrolled": seq.total_enrolled,
            "total_replied": seq.total_replied,
            "total_bounced": seq.total_bounced,
            "open_rate": open_rate,
            "reply_rate": reply_rate,
            "bounce_rate": bounce_rate,
            "per_step": per_step,
        }

    def email_performance(self, session: Session, user_id: int, days: int = 7) -> dict[str, int]:
        start = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(EmailEvent)
            .join(EmailAccount, EmailEvent.email_account_id == EmailAccount.id)
            .where(
                EmailEvent.created_at >= start,
                EmailAccount.user_id == user_id,
            )
        )
        events = session.execute(stmt).scalars().all()
        out = {"sent": 0, "delivered": 0, "opened": 0, "replied": 0, "bounced": 0, "failed": 0}
        for e in events:
            st = e.status
            if st == EmailEventStatus.SENT:
                out["sent"] += 1
            if st == EmailEventStatus.DELIVERED:
                out["delivered"] += 1
            if st == EmailEventStatus.OPENED or e.opened_at:
                out["opened"] += 1
            if st == EmailEventStatus.REPLIED or e.replied_at:
                out["replied"] += 1
            if st == EmailEventStatus.BOUNCED or e.bounced_at:
                out["bounced"] += 1
            if st == EmailEventStatus.FAILED:
                out["failed"] += 1
        return out
