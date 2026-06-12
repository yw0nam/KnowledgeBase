"""MCP input validators — coerce LLM "none"/"null"/"" strings to Python None.

Ported from conference_demo/src/core/mcp_validators.py.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator

_NONE_STRINGS = {"none", "null", ""}


def _coerce_none_string(v: Any) -> Any:
    """Return None when v is a string that represents a null-like value."""
    if isinstance(v, str) and v.strip().lower() in _NONE_STRINGS:
        return None
    return v


NullableBool = Annotated[bool | None, BeforeValidator(_coerce_none_string)]
NullableStr = Annotated[str | None, BeforeValidator(_coerce_none_string)]
NullableInt = Annotated[int | None, BeforeValidator(_coerce_none_string)]
NullableList = Annotated[list[Any] | None, BeforeValidator(_coerce_none_string)]


def require(**fields: Any) -> dict[str, Any] | None:
    """Return a retryable error dict if any field is missing/blank, else None."""
    missing = [
        n
        for n, v in fields.items()
        if v is None or (isinstance(v, str) and not v.strip())
    ]
    if missing:
        return {
            "error": (
                f"필수 인자가 누락되었습니다: {', '.join(missing)}."
                " 값을 채워서 다시 호출하세요."
            )
        }
    return None
