import asyncio
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.models.crm import DailyReport, EmailSequence
from app.schemas.analytics import (
    DailyReportOut,
    EmailPerformanceOut,
    PipelineSummaryOut,
    SequenceCompareOut,
    SequenceCompareRow,
)
from app.services.reporting import ReportingService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/pipeline", response_model=PipelineSummaryOut)
async def pipeline_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    scope: str = Query("mine", pattern="^(mine|all)$"),
):
    uid_mine = user.id

    def _run():
        from app.core.sync_db import sync_session_scope

        with sync_session_scope() as s:
            uid = uid_mine if scope == "mine" else None
            return ReportingService().get_pipeline_summary(s, uid)

    data = await asyncio.to_thread(_run)
    return PipelineSummaryOut(**data)


@router.get("/email-performance", response_model=EmailPerformanceOut)
async def email_performance(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    days: int = Query(7, ge=1, le=90),
):
    uid = user.id

    def _run():
        from app.core.sync_db import sync_session_scope

        with sync_session_scope() as s:
            return ReportingService().email_performance(s, uid, days)

    raw = await asyncio.to_thread(_run)
    return EmailPerformanceOut(period_days=days, **raw)


@router.get("/daily-report", response_model=DailyReportOut)
async def daily_report(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    report_date: date | None = None,
):
    rd = report_date or datetime.now(timezone.utc).date()
    uid = user.id

    def _run():
        from app.core.sync_db import sync_session_scope

        with sync_session_scope() as s:
            ReportingService().generate_daily_report(s, uid, rd)

    await asyncio.to_thread(_run)
    stmt = select(DailyReport).where(DailyReport.user_id == uid, DailyReport.report_date == rd)
    res = await db.execute(stmt)
    saved = res.scalar_one_or_none()
    if not saved:
        raise HTTPException(status_code=404, detail="Report not found")
    return saved


@router.get("/sequences/compare", response_model=SequenceCompareOut)
async def compare_sequences(db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    stmt = select(EmailSequence).where(EmailSequence.created_by_id == user.id)
    rows = await db.execute(stmt)
    seqs = list(rows.scalars().all())

    def perf(sid: int):
        from app.core.sync_db import sync_session_scope

        with sync_session_scope() as s:
            return ReportingService().get_sequence_performance(s, sid)

    out: list[SequenceCompareRow] = []
    for seq in seqs:
        p = await asyncio.to_thread(perf, seq.id)
        if not p:
            continue
        out.append(
            SequenceCompareRow(
                sequence_id=seq.id,
                name=seq.name,
                enrolled=p.get("total_enrolled", 0),
                open_rate=p.get("open_rate", 0),
                reply_rate=p.get("reply_rate", 0),
                bounce_rate=p.get("bounce_rate", 0),
            )
        )
    return SequenceCompareOut(sequences=out)
