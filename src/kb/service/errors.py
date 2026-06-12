"""Service-layer exceptions.

All service functions raise ``ServiceError`` instead of HTTP exceptions so
callers (CLI, MCP tools, tests) can handle failures without FastAPI.
"""

from __future__ import annotations

__all__ = ["ServiceError"]

_VALID_CODES = frozenset({"not_found", "conflict", "lint_failed", "export_failed"})


class ServiceError(Exception):
    """Machine-readable error from a service function.

    Attributes:
        code:   One of ``"not_found"``, ``"conflict"``, ``"lint_failed"``,
                ``"export_failed"``.
        detail: A str or dict describing the failure.
    """

    def __init__(self, code: str, detail: str | dict) -> None:
        if code not in _VALID_CODES:
            raise ValueError(
                f"invalid ServiceError code {code!r}; "
                f"expected one of {sorted(_VALID_CODES)}"
            )
        self.code = code
        self.detail = detail
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"
