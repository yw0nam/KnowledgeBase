"""Shared types and utilities for DB-backed lint."""

from __future__ import annotations
import re

REVIEW_STATUS_VALUES = frozenset({"not_processed", "pending_for_approve", "approved"})
REVIEW_STATUS_TYPES = frozenset(
    {"entity", "concept", "decision", "improvement", "checklist", "question"}
)
IMPROVEMENT_KIND_VALUES = frozenset({"improvement", "issue", "proposal"})
IMPROVEMENT_DOMAIN_VALUES = frozenset({"cost", "correctness", "perf", "dx", "security"})
IMPROVEMENT_SEVERITY_VALUES = frozenset({"low", "med", "high"})
IMPROVEMENT_ISSUE_STATUS_VALUES = frozenset(
    {"open", "acknowledged", "resolved", "wontfix"}
)

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

REQUIRED_FM_FIELDS = {
    "entity": ["type", "review_status", "created", "updated", "sources", "tags"],
    "concept": ["type", "review_status", "created", "updated", "sources", "tags"],
    "decision": ["type", "review_status", "created", "updated", "sources", "tags"],
    "improvement": [
        "type",
        "review_status",
        "kind",
        "observed_at",
        "domain",
        "severity",
        "issue_status",
        "related",
        "created",
        "updated",
        "sources",
        "tags",
    ],
    "checklist": ["type", "review_status", "created", "updated", "sources", "tags"],
    "summary": ["type", "created", "updated", "sources", "tags"],
    "question": ["type", "review_status", "created", "updated", "sources", "tags"],
}
STUB_THRESHOLD_CHARS = 100


def extract_wikilinks(body: str) -> list[str]:
    """Extract [[target]] and [[target|alias]] from body text."""
    return re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", body)


def parse_frontmatter_dict(fm: dict | None) -> dict:
    """Return fm as dict, or empty dict if None."""
    return fm if isinstance(fm, dict) else {}


class LintResult:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, identifier: str, msg: str):
        self.errors.append(f"  ERROR   {identifier}: {msg}")

    def warn(self, identifier: str, msg: str):
        self.warnings.append(f"  WARN    {identifier}: {msg}")

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0
