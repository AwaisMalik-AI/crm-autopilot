import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.models.crm import Contact, ContactSource
from app.schemas.contact import ContactBulkUpdate, ContactCreate, ContactOut, ContactUpdate

router = APIRouter(prefix="/contacts", tags=["contacts"])


def _parse_source(s: str) -> ContactSource:
    try:
        return ContactSource(s)
    except ValueError:
        return ContactSource.MANUAL


@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
async def create_contact(
    body: ContactCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    dup = await db.execute(select(Contact).where(Contact.email == body.email))
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Contact email exists")
    c = Contact(
        email=body.email,
        first_name=body.first_name,
        last_name=body.last_name,
        company=body.company,
        title=body.title,
        phone=body.phone,
        source=_parse_source(body.source),
        tags=list(body.tags or []),
        custom_fields=dict(body.custom_fields or {}),
        is_active=body.is_active,
        created_by_id=user.id,
    )
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return c


@router.get("", response_model=list[ContactOut])
async def list_contacts(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    skip: int = 0,
    limit: int = Query(50, le=200),
    q: str | None = None,
    tag: str | None = None,
):
    stmt = select(Contact).where(Contact.is_active.is_(True))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Contact.email).like(like),
                func.lower(func.coalesce(Contact.first_name, "")).like(like),
                func.lower(func.coalesce(Contact.company, "")).like(like),
            )
        )
    if tag:
        stmt = stmt.where(Contact.tags.contains([tag]))
    stmt = stmt.offset(skip).limit(limit).order_by(Contact.id.desc())
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


@router.get("/{contact_id}", response_model=ContactOut)
async def get_contact(contact_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    c = await db.get(Contact, contact_id)
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    return c


@router.patch("/{contact_id}", response_model=ContactOut)
async def update_contact(
    contact_id: int,
    body: ContactUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    c = await db.get(Contact, contact_id)
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if "source" in data and data["source"] is not None:
        data["source"] = _parse_source(data["source"])
    for k, v in data.items():
        setattr(c, k, v)
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return c


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(contact_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    c = await db.get(Contact, contact_id)
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    c.is_active = False
    db.add(c)


@router.post("/import/csv", response_model=list[ContactOut])
async def import_csv(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    file: UploadFile = File(...),
):
    raw = await file.read()
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    created: list[Contact] = []
    for row in reader:
        email = (row.get("email") or "").strip()
        if not email:
            continue
        exists = await db.execute(select(Contact).where(Contact.email == email))
        if exists.scalar_one_or_none():
            continue
        c = Contact(
            email=email,
            first_name=(row.get("first_name") or "").strip() or None,
            last_name=(row.get("last_name") or "").strip() or None,
            company=(row.get("company") or "").strip() or None,
            title=(row.get("title") or "").strip() or None,
            phone=(row.get("phone") or "").strip() or None,
            source=ContactSource.IMPORT,
            tags=[],
            custom_fields={},
            created_by_id=user.id,
        )
        db.add(c)
        created.append(c)
    await db.flush()
    for c in created:
        await db.refresh(c)
    return created


@router.post("/tags/bulk", response_model=list[ContactOut])
async def bulk_update(
    body: ContactBulkUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    stmt = select(Contact).where(Contact.id.in_(body.ids))
    rows = await db.execute(stmt)
    contacts = list(rows.scalars().all())
    for c in contacts:
        if body.tags_add:
            cur = list(c.tags or [])
            for t in body.tags_add:
                if t not in cur:
                    cur.append(t)
            c.tags = cur
        if body.tags_remove:
            cur = list(c.tags or [])
            c.tags = [t for t in cur if t not in set(body.tags_remove)]
        if body.is_active is not None:
            c.is_active = body.is_active
        if body.source is not None:
            c.source = _parse_source(body.source)
        db.add(c)
    await db.flush()
    return contacts


@router.post("/{contact_id}/tags/{tag}", response_model=ContactOut)
async def add_tag(contact_id: int, tag: str, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    c = await db.get(Contact, contact_id)
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    cur = list(c.tags or [])
    if tag not in cur:
        cur.append(tag)
    c.tags = cur
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return c


@router.delete("/{contact_id}/tags/{tag}", response_model=ContactOut)
async def remove_tag(contact_id: int, tag: str, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    c = await db.get(Contact, contact_id)
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    c.tags = [t for t in (c.tags or []) if t != tag]
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return c
