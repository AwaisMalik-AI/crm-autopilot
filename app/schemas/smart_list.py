from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SmartListBase(BaseModel):
    name: str
    filters: dict[str, Any] = Field(default_factory=dict)
    is_dynamic: bool = True


class SmartListCreate(SmartListBase):
    pass


class SmartListUpdate(BaseModel):
    name: str | None = None
    filters: dict[str, Any] | None = None
    is_dynamic: bool | None = None


class SmartListOut(SmartListBase):
    id: int
    contact_count: int
    last_refreshed_at: datetime | None
    created_by_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class SmartListPreviewRequest(BaseModel):
    filters: dict[str, Any] = Field(default_factory=dict)


class SmartListPreviewOut(BaseModel):
    matching_contact_ids: list[int]
    count: int
