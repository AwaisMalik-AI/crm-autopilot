from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class ContactBase(BaseModel):
    email: EmailStr
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    title: str | None = None
    phone: str | None = None
    source: str = "manual"
    tags: list[Any] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    title: str | None = None
    phone: str | None = None
    source: str | None = None
    tags: list[Any] | None = None
    custom_fields: dict[str, Any] | None = None
    is_active: bool | None = None


class ContactOut(ContactBase):
    id: int
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContactBulkUpdate(BaseModel):
    ids: list[int]
    tags_add: list[str] | None = None
    tags_remove: list[str] | None = None
    is_active: bool | None = None
    source: str | None = None
