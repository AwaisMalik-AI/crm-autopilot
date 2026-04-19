from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LeadBase(BaseModel):
    pipeline_stage: str = "new"
    source: str | None = None
    value_estimate: float | None = None
    notes: str | None = None


class LeadCreate(LeadBase):
    contact_id: int


class LeadUpdate(BaseModel):
    pipeline_stage: str | None = None
    assigned_to_id: int | None = None
    value_estimate: float | None = None
    notes: str | None = None
    source: str | None = None


class LeadOut(LeadBase):
    id: int
    contact_id: int
    score: int
    score_breakdown: dict[str, Any]
    assigned_to_id: int | None
    last_activity_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LeadActivityCreate(BaseModel):
    activity_type: str
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LeadActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    lead_id: int
    activity_type: str
    description: str | None = None
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_by_id: int | None = None
    created_at: datetime

    @classmethod
    def from_orm_activity(cls, obj) -> "LeadActivityOut":
        return cls(
            id=obj.id,
            lead_id=obj.lead_id,
            activity_type=obj.activity_type.value if hasattr(obj.activity_type, "value") else str(obj.activity_type),
            description=obj.description,
            metadata=obj.metadata_ or {},
            created_by_id=obj.created_by_id,
            created_at=obj.created_at,
        )


class ScoreResult(BaseModel):
    score: int
    breakdown: dict[str, Any]
