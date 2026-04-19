import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import verify_webhook_signature
from app.models.crm import (
    Contact,
    ContactSource,
    EmailEvent,
    EmailEventStatus,
    EmailSequence,
    EnrollmentStatus,
    Lead,
    LeadActivity,
    LeadActivityType,
    SequenceEnrollment,
)
from app.schemas.webhook import EmailEventWebhook, InboundContactWebhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/email-event", status_code=status.HTTP_200_OK)
async def email_event(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_signature: Annotated[str | None, Header(alias="X-Signature")] = None,
):
    body = await request.body()
    settings = get_settings()
    if not verify_webhook_signature(body, x_signature, settings.WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    evt = EmailEventWebhook.model_validate(payload)

    et = evt.event_type.lower()
    stmt = select(EmailEvent).where(EmailEvent.to_email == evt.to_email)
    if evt.message_id:
        stmt = stmt.where(EmailEvent.message_id == evt.message_id)
    stmt = stmt.order_by(EmailEvent.id.desc()).limit(1)
    row = await db.execute(stmt)
    ev = row.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Email event not found")

    now = datetime.now(timezone.utc)
    if et == "opened":
        ev.status = EmailEventStatus.OPENED
        ev.opened_at = now
    elif et == "replied":
        ev.status = EmailEventStatus.REPLIED
        ev.replied_at = now
    elif et == "bounced":
        ev.status = EmailEventStatus.BOUNCED
        ev.bounced_at = now
    elif et == "delivered":
        ev.status = EmailEventStatus.DELIVERED
    elif et == "failed":
        ev.status = EmailEventStatus.FAILED
    elif et == "clicked":
        ev.status = EmailEventStatus.CLICKED

    db.add(ev)

    if ev.enrollment_id and et == "replied":
        enr = await db.get(SequenceEnrollment, ev.enrollment_id)
        if enr:
            enr.status = EnrollmentStatus.REPLIED
            db.add(enr)
            seq = await db.get(EmailSequence, enr.sequence_id)
            if seq:
                seq.total_replied = (seq.total_replied or 0) + 1
                db.add(seq)

    if ev.enrollment_id and et in ("opened", "replied", "bounced"):
        enr = await db.get(SequenceEnrollment, ev.enrollment_id)
        if enr:
            lc = await db.execute(select(Lead).where(Lead.contact_id == enr.contact_id).limit(1))
            lead = lc.scalar_one_or_none()
            if lead:
                at_map = {
                    "opened": LeadActivityType.EMAIL_OPENED,
                    "replied": LeadActivityType.EMAIL_REPLIED,
                    "bounced": LeadActivityType.EMAIL_BOUNCED,
                }
                at = at_map.get(et)
                if at:
                    act = LeadActivity(
                        lead_id=lead.id,
                        activity_type=at,
                        description=f"Webhook: {et}",
                        metadata_=evt.metadata,
                    )
                    db.add(act)

    return {"ok": True, "event_id": ev.id}


@router.post("/inbound", status_code=status.HTTP_201_CREATED)
async def inbound_contact(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_signature: Annotated[str | None, Header(alias="X-Signature")] = None,
):
    body = await request.body()
    settings = get_settings()
    if not verify_webhook_signature(body, x_signature, settings.WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    data = InboundContactWebhook.model_validate(payload)

    exists = await db.execute(select(Contact).where(Contact.email == data.email))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Contact already exists")

    try:
        src = ContactSource(data.source)
    except ValueError:
        src = ContactSource.WEBHOOK

    c = Contact(
        email=data.email,
        first_name=data.first_name,
        last_name=data.last_name,
        company=data.company,
        title=data.title,
        phone=data.phone,
        source=src,
        tags=list(data.tags or []),
        custom_fields=dict(data.custom_fields or {}),
        created_by_id=None,
    )
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return {"id": c.id, "email": c.email}
