from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.models.crm import Contact, EmailEvent, EmailSequence, EnrollmentStatus, SequenceEnrollment, SequenceStatus
from app.schemas.sequence import (
    EmailSequenceCreate,
    EmailSequenceOut,
    EmailSequenceUpdate,
    EnrollContactsRequest,
    SequenceEnrollmentOut,
    SequencePerformanceOut,
)
from app.services.reporting import ReportingService

router = APIRouter(prefix="/sequences", tags=["sequences"])


def _seq_status(s: str) -> SequenceStatus:
    try:
        return SequenceStatus(s)
    except ValueError:
        return SequenceStatus.DRAFT


@router.post("", response_model=EmailSequenceOut, status_code=status.HTTP_201_CREATED)
async def create_sequence(
    body: EmailSequenceCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    seq = EmailSequence(
        name=body.name,
        description=body.description,
        steps=list(body.steps or []),
        status=_seq_status(body.status),
        created_by_id=user.id,
    )
    db.add(seq)
    await db.flush()
    await db.refresh(seq)
    return seq


@router.get("", response_model=list[EmailSequenceOut])
async def list_sequences(db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    stmt = select(EmailSequence).where(EmailSequence.created_by_id == user.id).order_by(EmailSequence.id.desc())
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


@router.get("/{sequence_id}", response_model=EmailSequenceOut)
async def get_sequence(sequence_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    seq = await db.get(EmailSequence, sequence_id)
    if not seq or seq.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    return seq


@router.patch("/{sequence_id}", response_model=EmailSequenceOut)
async def update_sequence(
    sequence_id: int,
    body: EmailSequenceUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    seq = await db.get(EmailSequence, sequence_id)
    if not seq or seq.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] is not None:
        data["status"] = _seq_status(data["status"])
    if "steps" in data and data["steps"] is not None:
        seq.steps = list(data["steps"])
        del data["steps"]
    for k, v in data.items():
        setattr(seq, k, v)
    db.add(seq)
    await db.flush()
    await db.refresh(seq)
    return seq


@router.delete("/{sequence_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sequence(sequence_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    seq = await db.get(EmailSequence, sequence_id)
    if not seq or seq.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    enr_ids = (
        await db.execute(select(SequenceEnrollment.id).where(SequenceEnrollment.sequence_id == sequence_id))
    ).scalars().all()
    for eid in enr_ids:
        await db.execute(delete(EmailEvent).where(EmailEvent.enrollment_id == eid))
    await db.execute(delete(SequenceEnrollment).where(SequenceEnrollment.sequence_id == sequence_id))
    await db.delete(seq)


@router.post("/{sequence_id}/enroll", response_model=list[SequenceEnrollmentOut])
async def enroll(
    sequence_id: int,
    body: EnrollContactsRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    seq = await db.get(EmailSequence, sequence_id)
    if not seq or seq.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    if seq.status != SequenceStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Sequence must be active to enroll")
    out: list[SequenceEnrollment] = []
    for cid in body.contact_ids:
        contact = await db.get(Contact, cid)
        if not contact:
            continue
        exists = await db.execute(
            select(SequenceEnrollment).where(
                SequenceEnrollment.sequence_id == sequence_id,
                SequenceEnrollment.contact_id == cid,
            )
        )
        if exists.scalar_one_or_none():
            continue
        enr = SequenceEnrollment(
            sequence_id=sequence_id,
            contact_id=cid,
            current_step=0,
            status=EnrollmentStatus.ACTIVE,
            next_send_at=datetime.now(timezone.utc),
        )
        db.add(enr)
        seq.total_enrolled += 1
        out.append(enr)
    db.add(seq)
    await db.flush()
    for e in out:
        await db.refresh(e)
    return out


@router.get("/{sequence_id}/performance", response_model=SequencePerformanceOut)
async def performance(sequence_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    seq = await db.get(EmailSequence, sequence_id)
    if not seq or seq.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")

    def _run():
        from app.core.sync_db import sync_session_scope

        with sync_session_scope() as s:
            return ReportingService().get_sequence_performance(s, sequence_id)

    import asyncio

    data = await asyncio.to_thread(_run)
    return SequencePerformanceOut(**data)


@router.post("/{sequence_id}/pause", response_model=EmailSequenceOut)
async def pause_sequence(sequence_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    seq = await db.get(EmailSequence, sequence_id)
    if not seq or seq.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    seq.status = SequenceStatus.PAUSED
    db.add(seq)
    await db.flush()
    await db.refresh(seq)
    return seq


@router.post("/{sequence_id}/resume", response_model=EmailSequenceOut)
async def resume_sequence(sequence_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    seq = await db.get(EmailSequence, sequence_id)
    if not seq or seq.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    seq.status = SequenceStatus.ACTIVE
    db.add(seq)
    await db.flush()
    await db.refresh(seq)
    return seq
