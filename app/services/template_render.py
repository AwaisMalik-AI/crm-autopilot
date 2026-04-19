"""Render {{var}} and {{custom.key}} templates for outreach."""

from __future__ import annotations

import re
from typing import Any

_VAR = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def render_template(template: str, contact: Any) -> str:
    """Replace variables from a Contact ORM object or dict-like contact."""

    def get_field(name: str) -> str:
        name = name.strip()
        if name.startswith("custom."):
            key = name.split(".", 1)[1]
            cf = _get_custom_fields(contact)
            return str(cf.get(key, ""))
        return str(_get_attr(contact, name) or "")

    def repl(m: re.Match[str]) -> str:
        return get_field(m.group(1))

    return _VAR.sub(repl, template)


def _get_attr(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _get_custom_fields(obj: Any) -> dict[str, Any]:
    cf = _get_attr(obj, "custom_fields")
    if isinstance(cf, dict):
        return cf
    return {}
