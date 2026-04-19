from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EmailSequenceBase(BaseModel):
    name: str
    description: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "draft"


class EmailSequenceCreate(EmailSequenceBase):
    pass


class EmailSequenceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[dict[str, Any]] | None = None
    status: str | None = None


class EmailSequenceOut(EmailSequenceBase):
    id: int
    total_enrolled: int
    total_replied: int
    total_bounced: int
    created_by_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class EnrollContactsRequest(BaseModel):
    contact_ids: list[int]


class SequenceEnrollmentOut(BaseModel):
    id: int
    sequence_id: int
    contact_id: int
    current_step: int
    status: str
    enrolled_at: datetime
    next_send_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class SequencePerformanceOut(BaseModel):
    sequence_id: int
    total_enrolled: int
    total_replied: int
    total_bounced: int
    open_rate: float
    reply_rate: float
    bounce_rate: float
    per_step: list[dict[str, Any]]
