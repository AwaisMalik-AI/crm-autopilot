"""Lead scoring: rules engine plus optional LLM narrative."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import httpx

from app.core.config import get_settings

if TYPE_CHECKING:
    from app.models.crm import Contact, Lead, LeadActivity

logger = logging.getLogger(__name__)


class LeadScorer:
    """Scores leads from engagement, recency, source, profile fit, and activity frequency."""

    def score(self, contact: Contact, lead: Lead, activities: list[LeadActivity]) -> dict[str, Any]:
        breakdown: dict[str, Any] = {}
        score = 0

        engagement = self._engagement_subscore(activities)
        breakdown["engagement"] = engagement
        score += engagement["points"]

        recency = self._recency_subscore(lead, activities)
        breakdown["recency"] = recency
        score += recency["points"]

        source_q = self._source_quality(lead, contact)
        breakdown["source_quality"] = source_q
        score += source_q["points"]

        profile = self._profile_fit(contact)
        breakdown["profile_fit"] = profile
        score += profile["points"]

        freq = self._activity_frequency(activities)
        breakdown["activity_frequency"] = freq
        score += freq["points"]

        score = max(0, min(100, int(round(score))))
        breakdown["total"] = score

        explanation = self._llm_explanation(contact, lead, breakdown)
        if explanation:
            breakdown["llm_explanation"] = explanation
        else:
            breakdown["llm_explanation"] = self._fallback_explanation(breakdown)

        return {"score": score, "breakdown": breakdown}

    def _engagement_subscore(self, activities: list) -> dict[str, Any]:
        def _at(a) -> str:
            t = a.activity_type
            return t.value if hasattr(t, "value") else str(t)

        opened = sum(1 for a in activities if _at(a) == "email_opened")
        replied = sum(1 for a in activities if _at(a) == "email_replied")
        bounced = sum(1 for a in activities if _at(a) == "email_bounced")
        points = min(35, opened * 5 + replied * 15)
        points -= min(20, bounced * 10)
        return {"opened": opened, "replied": replied, "bounced": bounced, "points": points}

    def _recency_subscore(self, lead, activities: list) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        refs: list[datetime] = []
        if lead.last_activity_at:
            la = lead.last_activity_at
            if la.tzinfo is None:
                la = la.replace(tzinfo=timezone.utc)
            refs.append(la)
        for a in activities[-20:]:
            ca = a.created_at
            if ca.tzinfo is None:
                ca = ca.replace(tzinfo=timezone.utc)
            refs.append(ca)
        if not refs:
            return {"days_since_activity": None, "points": 5}
        latest = max(refs)
        delta_days = (now - latest).total_seconds() / 86400
        if delta_days <= 1:
            pts = 20
        elif delta_days <= 7:
            pts = 15
        elif delta_days <= 30:
            pts = 8
        else:
            pts = 2
        return {"days_since_activity": round(delta_days, 2), "points": pts}

    def _source_quality(self, lead, contact) -> dict[str, Any]:
        cs = contact.source.value if hasattr(contact.source, "value") else str(contact.source)
        src = (lead.source or cs or "").lower()
        weights = {"linkedin": 12, "webhook": 10, "import": 6, "manual": 4}
        pts = 4
        for k, w in weights.items():
            if k in src:
                pts = w
                break
        return {"source": src or "unknown", "points": min(15, pts)}

    def _profile_fit(self, contact) -> dict[str, Any]:
        settings = get_settings()
        title_kw = [x.strip().lower() for x in settings.IDEAL_TITLE_KEYWORDS.split(",") if x.strip()]
        comp_kw = [x.strip().lower() for x in settings.IDEAL_COMPANY_KEYWORDS.split(",") if x.strip()]
        title = (contact.title or "").lower()
        company = (contact.company or "").lower()
        t_hit = sum(1 for k in title_kw if k and k in title)
        c_hit = sum(1 for k in comp_kw if k and k in company)
        pts = min(20, t_hit * 6 + c_hit * 4)
        return {"title_hits": t_hit, "company_hits": c_hit, "points": pts}

    def _activity_frequency(self, activities: list) -> dict[str, Any]:
        n = len(activities)
        if n >= 15:
            pts = 10
        elif n >= 8:
            pts = 7
        elif n >= 3:
            pts = 4
        else:
            pts = 1
        return {"count": n, "points": pts}

    def _fallback_explanation(self, breakdown: dict[str, Any]) -> str:
        parts = [
            f"Engagement contributes {breakdown['engagement']['points']} pts (opens/replies/bounces).",
            f"Recency adds {breakdown['recency']['points']} pts.",
            f"Source quality {breakdown['source_quality']['points']} pts.",
            f"Profile fit {breakdown['profile_fit']['points']} pts.",
            f"Activity frequency {breakdown['activity_frequency']['points']} pts.",
        ]
        return " ".join(parts)

    def _llm_explanation(self, contact: Contact, lead: Lead, breakdown: dict[str, Any]) -> str | None:
        settings = get_settings()
        if not settings.LLM_API_URL or not settings.LLM_API_KEY:
            return None
        prompt = (
            "You are a sales analyst. In 2-4 sentences, explain why this lead received this score. "
            "Be specific to the breakdown JSON. No PII beyond role/company level.\n"
            f"Contact summary: company={contact.company!r}, title={contact.title!r}\n"
            f"Lead stage={lead.pipeline_stage.value}, source={lead.source!r}\n"
            f"Breakdown JSON: {json.dumps(breakdown, default=str)[:6000]}"
        )
        try:
            with httpx.Client(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                # OpenAI-compatible chat completions
                r = client.post(
                    str(settings.LLM_API_URL).rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
                    json={
                        "model": settings.LLM_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                    },
                )
                r.raise_for_status()
                data = r.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("LLM scoring explanation failed: %s", exc)
            return None
