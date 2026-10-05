from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser
from app.services.outreach_crew import OutreachCrew
from app.tasks.crew_tasks import run_outreach_crew_task

router = APIRouter(prefix="/crews", tags=["crews"])


class OutreachRequest(BaseModel):
    company: str = Field(..., min_length=2, max_length=200)
    persona: str = Field(default="Founder", max_length=120)
    offer: str = Field(..., min_length=3, max_length=500)
    extras: dict[str, Any] = Field(default_factory=dict)
    async_run: bool = False


class OutreachResponse(BaseModel):
    crew: str
    used_llm: bool
    steps: list[dict[str, Any]]
    subject: str
    body: str
    compliance_notes: str
    task_id: str | None = None


@router.post("/outreach", response_model=OutreachResponse)
async def run_outreach(body: OutreachRequest, _: CurrentUser) -> OutreachResponse:
    if body.async_run:
        task = run_outreach_crew_task.delay(body.company, body.persona, body.offer, body.extras)
        return OutreachResponse(
            crew="outreach",
            used_llm=False,
            steps=[],
            subject="queued",
            body="queued",
            compliance_notes="",
            task_id=task.id,
        )
    result = OutreachCrew().run(body.company, body.persona, body.offer, body.extras)
    return OutreachResponse(
        crew=result.crew,
        used_llm=result.used_llm,
        steps=result.steps,
        subject=result.subject,
        body=result.body,
        compliance_notes=result.compliance_notes,
    )
