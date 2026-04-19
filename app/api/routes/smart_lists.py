import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.models.crm import SmartList
from app.schemas.smart_list import (
    SmartListCreate,
    SmartListOut,
    SmartListPreviewOut,
    SmartListPreviewRequest,
    SmartListUpdate,
)
from app.services.smart_list_engine import SmartListEngine

router = APIRouter(prefix="/smart-lists", tags=["smart-lists"])


@router.post("", response_model=SmartListOut, status_code=status.HTTP_201_CREATED)
async def create_list(
    body: SmartListCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    sl = SmartList(
        name=body.name,
        filters=dict(body.filters or {}),
        is_dynamic=body.is_dynamic,
        created_by_id=user.id,
    )
    db.add(sl)
    await db.flush()
    await db.refresh(sl)
    return sl


@router.get("", response_model=list[SmartListOut])
async def list_smart_lists(db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    stmt = select(SmartList).where(SmartList.created_by_id == user.id).order_by(SmartList.id.desc())
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


@router.get("/{list_id}", response_model=SmartListOut)
async def get_smart_list(list_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    sl = await db.get(SmartList, list_id)
    if not sl or sl.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    return sl


@router.patch("/{list_id}", response_model=SmartListOut)
async def update_smart_list(
    list_id: int,
    body: SmartListUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    sl = await db.get(SmartList, list_id)
    if not sl or sl.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if "filters" in data and data["filters"] is not None:
        sl.filters = dict(data["filters"])
        del data["filters"]
    for k, v in data.items():
        setattr(sl, k, v)
    db.add(sl)
    await db.flush()
    await db.refresh(sl)
    return sl


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_smart_list(list_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    sl = await db.get(SmartList, list_id)
    if not sl or sl.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(sl)


@router.post("/{list_id}/refresh", response_model=SmartListOut)
async def refresh_list(list_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    sl = await db.get(SmartList, list_id)
    if not sl or sl.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")

    def _run():
        from app.core.sync_db import sync_session_scope

        with sync_session_scope() as s:
            row = s.get(SmartList, list_id)
            if not row:
                return None
            SmartListEngine().refresh(s, row)
            s.refresh(row)
            return row

    updated = await asyncio.to_thread(_run)
    if not updated:
        raise HTTPException(status_code=404, detail="Not found")
    await db.refresh(sl)
    sl = await db.get(SmartList, list_id)
    return sl


@router.post("/preview", response_model=SmartListPreviewOut)
async def preview_filters(
    body: SmartListPreviewRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    filters = body.filters or {}

    def _run():
        from app.core.sync_db import sync_session_scope

        with sync_session_scope() as s:
            ids = SmartListEngine().preview(s, filters)
            return ids

    ids = await asyncio.to_thread(_run)
    return SmartListPreviewOut(matching_contact_ids=ids, count=len(ids))
