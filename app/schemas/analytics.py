from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class PipelineStageSummary(BaseModel):
    stage: str
    count: int


class PipelineSummaryOut(BaseModel):
    stages: list[PipelineStageSummary]
    conversion_rates: dict[str, float]


class EmailPerformanceOut(BaseModel):
    period_days: int
    sent: int
    delivered: int
    opened: int
    replied: int
    bounced: int
    failed: int


class DailyReportOut(BaseModel):
    id: int
    user_id: int
    report_date: date
    emails_sent: int
    emails_opened: int
    replies_received: int
    new_leads: int
    leads_moved: int
    summary_text: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SequenceCompareRow(BaseModel):
    sequence_id: int
    name: str
    enrolled: int
    open_rate: float
    reply_rate: float
    bounce_rate: float


class SequenceCompareOut(BaseModel):
    sequences: list[SequenceCompareRow]


class DailyReportQuery(BaseModel):
    report_date: date | None = None
