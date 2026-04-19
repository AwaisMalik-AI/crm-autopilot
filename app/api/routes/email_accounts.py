import asyncio
import smtplib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.security import decrypt_secret, encrypt_secret
from app.models.crm import EmailAccount, EmailAccountHealth
from app.schemas.email_account import EmailAccountCreate, EmailAccountOut, EmailAccountUpdate, WarmupStatusOut
from app.services.email_engine import EmailEngine

router = APIRouter(prefix="/email-accounts", tags=["email-accounts"])


@router.post("", response_model=EmailAccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    body: EmailAccountCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    acc = EmailAccount(
        user_id=user.id,
        email=body.email,
        smtp_host=body.smtp_host,
        smtp_port=body.smtp_port,
        smtp_user=body.smtp_user,
        smtp_password_encrypted=encrypt_secret(body.smtp_password),
        daily_limit=body.daily_limit,
        warmup_max_per_day=body.warmup_max_per_day,
        is_active=body.is_active,
        health_status=EmailAccountHealth.HEALTHY,
    )
    db.add(acc)
    await db.flush()
    await db.refresh(acc)
    return acc


@router.get("", response_model=list[EmailAccountOut])
async def list_accounts(db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    stmt = select(EmailAccount).where(EmailAccount.user_id == user.id).order_by(EmailAccount.id.desc())
    rows = await db.execute(stmt)
    return list(rows.scalars().all())


@router.get("/{account_id}", response_model=EmailAccountOut)
async def get_account(account_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    acc = await db.get(EmailAccount, account_id)
    if not acc or acc.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    return acc


@router.patch("/{account_id}", response_model=EmailAccountOut)
async def update_account(
    account_id: int,
    body: EmailAccountUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    acc = await db.get(EmailAccount, account_id)
    if not acc or acc.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if "smtp_password" in data and data["smtp_password"]:
        acc.smtp_password_encrypted = encrypt_secret(data.pop("smtp_password"))
    for k, v in data.items():
        setattr(acc, k, v)
    db.add(acc)
    await db.flush()
    await db.refresh(acc)
    return acc


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(account_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    acc = await db.get(EmailAccount, account_id)
    if not acc or acc.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(acc)


@router.post("/{account_id}/health-check")
async def health_check(account_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    acc = await db.get(EmailAccount, account_id)
    if not acc or acc.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")

    def _probe():
        settings = get_settings()
        pwd = decrypt_secret(acc.smtp_password_encrypted)
        try:
            if acc.smtp_port == 465:
                with smtplib.SMTP_SSL(acc.smtp_host, acc.smtp_port, timeout=20) as smtp:
                    smtp.login(acc.smtp_user, pwd)
            else:
                with smtplib.SMTP(acc.smtp_host, acc.smtp_port, timeout=20) as smtp:
                    if settings.SMTP_USE_TLS:
                        smtp.starttls()
                    smtp.login(acc.smtp_user, pwd)
            return "healthy"
        except Exception:
            return "failed"

    result = await asyncio.to_thread(_probe)
    acc.health_status = EmailAccountHealth.HEALTHY if result == "healthy" else EmailAccountHealth.WARNING
    db.add(acc)
    await db.flush()
    return {"account_id": account_id, "smtp": result, "health_status": acc.health_status.value}


@router.get("/{account_id}/warmup", response_model=WarmupStatusOut)
async def warmup_status(account_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser):
    acc = await db.get(EmailAccount, account_id)
    if not acc or acc.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    engine = EmailEngine()
    settings = get_settings()
    if settings.WARMUP_ENABLED:
        cap = min(acc.daily_limit, max(acc.warmup_max_per_day, acc.warmup_stage * 3 + 5))
    else:
        cap = acc.daily_limit
    return WarmupStatusOut(
        account_id=acc.id,
        warmup_stage=acc.warmup_stage,
        warmup_max_per_day=acc.warmup_max_per_day,
        effective_daily_cap=cap,
        sent_today=acc.sent_today,
        eligible_to_send=engine.check_warmup_eligibility(acc),
    )
