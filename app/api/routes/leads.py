import asyncio
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.models.crm import Lead, LeadActivity, LeadActivityType, PipelineStage
from app.schemas.lead import (
    LeadActivityCreate,
    LeadActivityOut,
    LeadCreate,
    LeadOut,
    LeadUpdate,
    ScoreResult,
)
from app.services.lead_scorer import LeadScorer

router = APIRouter(prefix="/leads", tags=["leads"])


def _stage(s: str) -> PipelineStage:
    try:
        return PipelineStage(s)
    except ValueError:
        return PipelineStage.NEW


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
async def create_lead(body: LeadCreate, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    lead = Lead(
        contact_id=body.contact_id,
        pipeline_stage=_stage(body.pipeline_stage),
        source=body.source,
        value_estimate=body.value_estimate,
        notes=body.notes,
        assigned_to_id=user.id,
    )
    db.add(lead)
    await db.flush()
    await db.refresh(lead)
    return lead


@router.get("", response_model=list[LeadOut])
async def list_leads(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    stage: str | None = None,
    assigned_to: int | None = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
):
    stmt = select(Lead)
    if stage:
        stmt = stmt.where(Lead.pipeline_stage == _stage(stage))
    if assigned_to is not None:
        stmt = stmt.where(Lead.assigned_to_id == assigned_to)
    else:
        stmt = stmt.where(Lead.assigned_to_id == user.id)
    stmt = stmt.offset(skip).limit(limit).order_by(Lead.id.desc())
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


@router.get("/{lead_id}", response_model=LeadOut)
async def get_lead(lead_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")
    return lead


@router.patch("/{lead_id}", response_model=LeadOut)
async def update_lead(
    lead_id: int,
    body: LeadUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")
    prev_stage = lead.pipeline_stage
    data = body.model_dump(exclude_unset=True)
    if "pipeline_stage" in data and data["pipeline_stage"] is not None:
        data["pipeline_stage"] = _stage(data["pipeline_stage"])
    for k, v in data.items():
        setattr(lead, k, v)
    if "pipeline_stage" in data and data["pipeline_stage"] != prev_stage:
        act = LeadActivity(
            lead_id=lead.id,
            activity_type=LeadActivityType.STAGE_CHANGE,
            description=f"{prev_stage.value} -> {lead.pipeline_stage.value}",
            metadata_={"from": prev_stage.value, "to": lead.pipeline_stage.value},
            created_by_id=user.id,
        )
        db.add(act)
    lead.last_activity_at = datetime.now(timezone.utc)
    db.add(lead)
    await db.flush()
    await db.refresh(lead)
    return lead


@router.post("/{lead_id}/assign", response_model=LeadOut)
async def assign_lead(
    lead_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    assignee_id: int = Query(..., description="User id to assign"),
):
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")
    lead.assigned_to_id = assignee_id
    lead.last_activity_at = datetime.now(timezone.utc)
    db.add(lead)
    await db.flush()
    await db.refresh(lead)
    return lead


@router.post("/{lead_id}/score", response_model=ScoreResult)
async def score_lead(lead_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    stmt = (
        select(Lead)
        .options(selectinload(Lead.contact), selectinload(Lead.activities))
        .where(Lead.id == lead_id)
    )
    lead = (await db.execute(stmt)).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")
    scorer = LeadScorer()
    result = await asyncio.to_thread(scorer.score, lead.contact, lead, list(lead.activities))
    lead.score = result["score"]
    lead.score_breakdown = result["breakdown"]
    lead.last_activity_at = datetime.now(timezone.utc)
    db.add(lead)
    await db.flush()
    return ScoreResult(score=result["score"], breakdown=result["breakdown"])


@router.get("/{lead_id}/activities", response_model=list[LeadActivityOut])
async def list_activities(lead_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")
    stmt = select(LeadActivity).where(LeadActivity.lead_id == lead_id).order_by(LeadActivity.id.desc())
    rows = await db.execute(stmt)
    return [LeadActivityOut.from_orm_activity(a) for a in rows.scalars().all()]


@router.post("/{lead_id}/activities", response_model=LeadActivityOut, status_code=status.HTTP_201_CREATED)
async def add_activity(
    lead_id: int,
    body: LeadActivityCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        at = LeadActivityType(body.activity_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid activity_type")
    act = LeadActivity(
        lead_id=lead_id,
        activity_type=at,
        description=body.description,
        metadata_=body.metadata,
        created_by_id=user.id,
    )
    db.add(act)
    lead.last_activity_at = datetime.now(timezone.utc)
    db.add(lead)
    await db.flush()
    await db.refresh(act)
    return LeadActivityOut.from_orm_activity(act)
