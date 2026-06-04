"""DB-backed handoff document validators."""

from __future__ import annotations

import re

from kb.lint.common import LintResult

RECOMMENDED_ROLES = {"opencode", "claude_code", "hermes", "user"}
VALID_STATUSES = {"draft", "ready", "consumed", "superseded"}
VALID_PROMOTIONS = {None, "skill_candidate", "memory", "wiki_entity", "wiki_concept"}

REQUIRED_FM_KEYS = [
    "handoff_id",
    "task_slug",
    "subject",
    "role",
    "handoff_seq",
    "status",
    "security",
    "promotion",
]

HANDOFF_ID_RE = re.compile(r"^[a-z0-9-]+:(?:[a-z0-9-]+|null):[a-z][a-z0-9_-]*:\d{2}$")

CANONICAL_BODY_SECTIONS = [
    "## 1. Assignment",
    "## 2. Context received",
    "## 3. Work performed",
    "## 4. Tool trace",
    "## 5. Findings / decisions",
    "## 6. Outputs",
    "## 7. Verification",
    "## 8. Risks / uncertainties",
    "## 9. Next handoff instructions",
    "## 10. Promotion candidates",
]

TOOL_TRACE_PIPE_COUNT = 8


def validate_handoff_create(fm: dict | None, body_md: str) -> LintResult:
    """Validate a handoff document at create time.

    All checks are self-contained (no cross-document scanning needed).
    """
    result = LintResult()

    if not isinstance(fm, dict):
        result.error(
            "(no frontmatter)", "missing or invalid frontmatter (must be a dict)"
        )
        return result
    if not fm:
        result.error("(no frontmatter)", "missing or empty frontmatter")
        return result

    _check_required_keys(result, fm)
    _check_role(result, fm)
    _check_status(result, fm)
    _check_promotion(result, fm)
    _check_handoff_id(result, fm)
    _check_security(result, fm)
    _check_canonical_sections(result, body_md)
    _check_tool_trace(result, body_md)

    return result


def _check_required_keys(result: LintResult, fm: dict) -> None:
    identifier = fm.get("handoff_id", "(no handoff_id)")
    for key in REQUIRED_FM_KEYS:
        if key not in fm:
            result.error(identifier, f"missing frontmatter field: {key}")


def _check_role(result: LintResult, fm: dict) -> None:
    identifier = fm.get("handoff_id", "(no handoff_id)")
    role = fm.get("role")
    if role is not None and role not in RECOMMENDED_ROLES:
        result.warn(
            identifier,
            f"uncommon role: {role!r} (recommended: {sorted(RECOMMENDED_ROLES)})",
        )


def _check_status(result: LintResult, fm: dict) -> None:
    identifier = fm.get("handoff_id", "(no handoff_id)")
    status = fm.get("status")
    if status is not None and status not in VALID_STATUSES:
        result.error(
            identifier,
            f"invalid status: {status!r} (must be one of {sorted(VALID_STATUSES)})",
        )


def _check_promotion(result: LintResult, fm: dict) -> None:
    identifier = fm.get("handoff_id", "(no handoff_id)")
    promotion = fm.get("promotion")
    if promotion is not None and promotion not in VALID_PROMOTIONS:
        result.error(
            identifier,
            f"invalid promotion: {promotion!r} "
            f"(must be null|skill_candidate|memory|wiki_entity|wiki_concept)",
        )


def _check_handoff_id(result: LintResult, fm: dict) -> None:
    identifier = fm.get("handoff_id", "(no handoff_id)")
    handoff_id = fm.get("handoff_id")
    if isinstance(handoff_id, str) and not HANDOFF_ID_RE.match(handoff_id):
        result.error(
            identifier,
            f"handoff_id format invalid: {handoff_id!r} "
            f"(expected '<task-slug>:<subject-or-null>:<role>:<NN>')",
        )


def _check_security(result: LintResult, fm: dict) -> None:
    identifier = fm.get("handoff_id", "(no handoff_id)")
    sec = fm.get("security")
    if sec is None:
        return

    if not isinstance(sec, dict):
        result.error(identifier, "security must be a YAML mapping")
        return

    if "contains_secrets" not in sec:
        result.error(identifier, "security.contains_secrets missing")
    elif not isinstance(sec["contains_secrets"], bool):
        result.error(
            identifier,
            f"security.contains_secrets must be bool, "
            f"got {type(sec['contains_secrets']).__name__}",
        )

    if "redaction_status" not in sec:
        result.error(identifier, "security.redaction_status missing")
    elif not isinstance(sec["redaction_status"], str):
        result.error(
            identifier,
            f"security.redaction_status must be string, "
            f"got {type(sec['redaction_status']).__name__}",
        )

    contains_secrets = sec.get("contains_secrets")
    redaction_status = sec.get("redaction_status")
    promotion = fm.get("promotion")

    if promotion in {"wiki_entity", "wiki_concept"} and contains_secrets is True:
        result.error(
            identifier,
            f"promotion={promotion!r} forbidden when "
            f"security.contains_secrets is true",
        )
    if promotion == "memory" and redaction_status == "unchecked":
        result.error(
            identifier,
            "promotion='memory' forbidden when "
            "security.redaction_status is 'unchecked'",
        )


def _check_canonical_sections(result: LintResult, body: str) -> None:
    identifier = "(no handoff_id)"
    missing_sections = [s for s in CANONICAL_BODY_SECTIONS if s not in body]
    if missing_sections:
        result.warn(
            identifier,
            f"missing canonical body sections: {', '.join(missing_sections)}",
        )


def _check_tool_trace(result: LintResult, body: str) -> None:
    marker = "## 4. Tool trace"
    idx = body.find(marker)
    if idx < 0:
        return

    section = body[idx + len(marker) :]
    next_h = re.search(r"^##\s+", section, re.MULTILINE)
    if next_h:
        section = section[: next_h.start()]

    table_lines = [ln for ln in section.splitlines() if ln.lstrip().startswith("|")]
    if not table_lines:
        return

    header = table_lines[0]
    if header.count("|") != TOOL_TRACE_PIPE_COUNT:
        result.warn(
            "(no handoff_id)",
            f"tool trace table header has {header.count('|')} pipes, "
            f"expected {TOOL_TRACE_PIPE_COUNT}",
        )
