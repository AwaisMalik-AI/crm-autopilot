"""Dynamic smart lists: filter evaluation and refresh."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crm import Contact, SmartList


class SmartListEngine:
    """Evaluate JSON filter rules against contacts."""

    def refresh(self, session: Session, smart_list: SmartList) -> SmartList:
        contacts = session.execute(select(Contact).where(Contact.is_active.is_(True))).scalars().all()
        matching = [c for c in contacts if self.evaluate_filters(smart_list.filters or {}, c)]
        smart_list.contact_count = len(matching)
        smart_list.last_refreshed_at = datetime.now(timezone.utc)
        session.add(smart_list)
        session.flush()
        return smart_list

    def preview(self, session: Session, filters: dict[str, Any]) -> list[int]:
        contacts = session.execute(select(Contact).where(Contact.is_active.is_(True))).scalars().all()
        return [c.id for c in contacts if self.evaluate_filters(filters or {}, c)]

    def evaluate_filters(self, filters: dict[str, Any], contact: Contact) -> bool:
        rules = filters.get("rules")
        if not rules:
            return True
        combiner = (filters.get("combiner") or "and").lower()

        results: list[bool] = []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            field = rule.get("field")
            operator = (rule.get("operator") or "equals").lower()
            value = rule.get("value")
            results.append(self._apply_rule(contact, field, operator, value))

        if not results:
            return True
        if combiner == "or":
            return any(results)
        return all(results)

    def _apply_rule(self, contact: Contact, field: str | None, operator: str, value: Any) -> bool:
        if not field:
            return True
        actual = self._resolve_field(contact, field)
        op = operator

        if op == "equals":
            return self._norm(actual) == self._norm(value)
        if op == "contains":
            return value is not None and str(value).lower() in str(actual or "").lower()
        if op == "greater_than":
            return self._num(actual) > self._num(value)
        if op == "less_than":
            return self._num(actual) < self._num(value)
        if op == "in_list":
            vals = value if isinstance(value, list) else str(value).split(",")
            return str(actual) in [str(v).strip() for v in vals]
        if op == "not_empty":
            return actual is not None and str(actual).strip() != ""
        if op == "date_before":
            return self._date(actual) < self._date(value)
        if op == "date_after":
            return self._date(actual) > self._date(value)
        return False

    def _resolve_field(self, contact: Contact, field: str) -> Any:
        if field.startswith("custom."):
            key = field.split(".", 1)[1]
            return (contact.custom_fields or {}).get(key)
        if field == "tags":
            return contact.tags or []
        if hasattr(contact, field):
            val = getattr(contact, field)
            if hasattr(val, "value"):
                return val.value
            return val
        return None

    def _norm(self, v: Any) -> str:
        return str(v).strip().lower() if v is not None else ""

    def _num(self, v: Any) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    def _date(self, v: Any):
        from datetime import date as date_cls

        if hasattr(v, "date") and callable(v.date):
            try:
                return v.date()
            except Exception:
                pass
        if isinstance(v, date_cls):
            return v
        if isinstance(v, str):
            return date_cls.fromisoformat(v[:10])
        return date_cls.min
