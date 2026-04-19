from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class EmailAccountBase(BaseModel):
    email: EmailStr
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str
    daily_limit: int = Field(default=50, ge=1, le=5000)
    warmup_max_per_day: int = Field(default=5, ge=1, le=500)
    is_active: bool = True


class EmailAccountCreate(EmailAccountBase):
    smtp_password: str = Field(..., min_length=1)


class EmailAccountUpdate(BaseModel):
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    daily_limit: int | None = Field(default=None, ge=1, le=5000)
    warmup_max_per_day: int | None = Field(default=None, ge=1, le=500)
    is_active: bool | None = None


class EmailAccountOut(BaseModel):
    id: int
    user_id: int
    email: EmailStr
    smtp_host: str
    smtp_port: int
    smtp_user: str
    daily_limit: int
    sent_today: int
    warmup_stage: int
    warmup_max_per_day: int
    is_active: bool
    health_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WarmupStatusOut(BaseModel):
    account_id: int
    warmup_stage: int
    warmup_max_per_day: int
    effective_daily_cap: int
    sent_today: int
    eligible_to_send: bool
