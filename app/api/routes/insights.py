from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser
from app.services.next_best_action import recommend

router = APIRouter(prefix="/insights", tags=["insights"])


class NBARequest(BaseModel):
    stage: str = Field(default="new")
    score: int = Field(default=0, ge=0, le=100)
    last_activity: str = ""
    days_since_touch: int = Field(default=3, ge=0, le=365)


@router.post("/next-best-action")
async def next_best_action(body: NBARequest, _: CurrentUser) -> dict[str, Any]:
    return {"kind": "next_best_action", **recommend(body.stage, body.score, body.last_activity, body.days_since_touch)}
