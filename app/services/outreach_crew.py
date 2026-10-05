"""Outreach crew: researcher → copywriter → compliance reviewer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import get_settings


@dataclass
class CrewResult:
    crew: str = "outreach"
    used_llm: bool = False
    steps: list[dict[str, Any]] = field(default_factory=list)
    subject: str = ""
    body: str = ""
    compliance_notes: str = ""


def _has_llm_key() -> bool:
    try:
        return bool(get_settings().LLM_API_KEY)
    except Exception:
        return False


def _llm(system: str, user: str) -> str | None:
    try:
        s = get_settings()
    except Exception:
        return None
    if not s.LLM_API_KEY:
        return None
    url = (s.LLM_API_URL or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    try:
        with httpx.Client(timeout=s.LLM_TIMEOUT_SECONDS) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {s.LLM_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": s.LLM_MODEL,
                    "temperature": 0.4,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception:
        return None


class OutreachCrew:
    def run(self, company: str, persona: str, offer: str, extras: dict[str, Any] | None = None) -> CrewResult:
        extras = extras or {}
        research = _llm(
            "You research a prospect. Return 4 bullets: pain, trigger, objection, hook.",
            f"Company={company} Persona={persona} Offer={offer} Extra={extras}",
        ) or (
            f"Pain: {persona} at {company} likely cares about pipeline speed. "
            f"Trigger: recent hiring/growth. Objection: 'already have a tool'. Hook: {offer}."
        )
        copy = _llm(
            "Write a 90-word cold email. Subject on first line as 'Subject: ...'. No hype.",
            f"Research:\n{research}",
        ) or (
            f"Subject: quick idea for {company}\n\n"
            f"Hi — noticed {company} is scaling. We help {persona.lower()}s with {offer}. "
            f"Worth a 15-minute look this week?"
        )
        review = _llm(
            "Compliance reviewer. Flag spam words, false claims, and missing opt-out.",
            copy,
        ) or "Compliance: keep claims specific, add a one-click opt-out, avoid urgency spam."
        subject = "quick idea"
        body = copy
        if "Subject:" in copy:
            first, _, rest = copy.partition("\n")
            subject = first.replace("Subject:", "").strip() or subject
            body = rest.strip() or copy
        return CrewResult(
            used_llm=_has_llm_key(),
            steps=[
                {"agent": "researcher", "output": research},
                {"agent": "copywriter", "output": copy},
                {"agent": "compliance", "output": review},
            ],
            subject=subject,
            body=body,
            compliance_notes=review,
        )
