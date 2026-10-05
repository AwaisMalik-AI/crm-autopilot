"""Next-best-action for a lead based on stage, score, and last activity."""

from __future__ import annotations

from typing import Any


def recommend(stage: str, score: int = 0, last_activity: str = "", days_since_touch: int = 3) -> dict[str, Any]:
    stage = (stage or "new").lower()
    act = (last_activity or "").lower()
    if score >= 80 and stage in {"new", "contacted"}:
        action, why = "book_demo", "High-intent lead — move to a live conversation."
    elif days_since_touch >= 7:
        action, why = "reengage_email", "Gone quiet. Send a short bump with a single ask."
    elif "opened" in act or "clicked" in act:
        action, why = "call_now", "Recent engagement — call while interest is warm."
    elif stage in {"qualified", "proposal"}:
        action, why = "send_case_study", "Deal is mid-funnel; social proof unsticks replies."
    else:
        action, why = "nurture_sequence", "Keep the lead in a light 3-step sequence."
    return {
        "action": action,
        "reason": why,
        "priority": "high" if score >= 70 or days_since_touch >= 7 else "medium",
        "suggested_channel": "phone" if action == "call_now" else "email",
    }
