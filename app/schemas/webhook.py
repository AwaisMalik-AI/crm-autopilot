from typing import Any

from pydantic import BaseModel, EmailStr, Field


class EmailEventWebhook(BaseModel):
    """Inbound tracking provider payload (normalized)."""

    message_id: str | None = None
    to_email: EmailStr
    event_type: str = Field(
        ...,
        description="opened|clicked|replied|bounced|delivered|failed",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class InboundContactWebhook(BaseModel):
    email: EmailStr
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    title: str | None = None
    phone: str | None = None
    source: str = "webhook"
    tags: list[str] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
