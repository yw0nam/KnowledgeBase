"""Validation helpers for handoff linting."""

from __future__ import annotations

import re

# Recommended values only; non-members warn but are not rejected.
RECOMMENDED_ROLES = {
    "opencode",
    "claude_code",
    "hermes",
    "user",
}
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

HANDOFF_ID_RE = re.compile(
    r"^[a-z0-9-]+:(?:[a-z0-9-]+|null):"
    r"[a-z][a-z0-9_-]*:\d{2}$"
)

HANDOFF_FILENAME_RE = re.compile(
    r"^(?:(?P<subject>[a-z0-9-]+)_)?"
    r"(?P<role>[a-z][a-z0-9_-]*)"
    r"_handoff_(?P<seq>\d{2})\.md$"
)
FINAL_FILENAME_RE = re.compile(r"^(?P<slug>[a-z0-9-]+)_final\.md$")

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

# 7 logical columns + 2 outer pipes = 8 pipe characters per row.
TOOL_TRACE_PIPE_COUNT = 8


def _security_flags(fm: dict) -> tuple[bool | None, str | None]:
    sec = fm.get("security")
    if not isinstance(sec, dict):
        return None, None
    contains = sec.get("contains_secrets")
    redaction = sec.get("redaction_status")
    contains_val = contains if isinstance(contains, bool) else None
    redaction_val = redaction if isinstance(redaction, str) else None
    return contains_val, redaction_val


def _validate_handoff(
    result,
    rel: str,
    fm: dict,
    role_from_filename: str,
    seq_from_filename: int,
    body: str,
) -> None:
    for key in REQUIRED_FM_KEYS:
        if key not in fm:
            result.error(rel, f"missing frontmatter field: {key}")

    role = fm.get("role")
    if "role" in fm and role not in RECOMMENDED_ROLES:
        result.warn(
            rel,
            f"uncommon role: {role!r} (recommended: {sorted(RECOMMENDED_ROLES)})",
        )

    status = fm.get("status")
    if "status" in fm and status not in VALID_STATUSES:
        result.error(
            rel,
            f"invalid status: {status!r} (must be one of {sorted(VALID_STATUSES)})",
        )

    if "promotion" in fm:
        promotion = fm.get("promotion")
        if promotion not in VALID_PROMOTIONS:
            result.error(
                rel,
                f"invalid promotion: {promotion!r} "
                f"(must be null|skill_candidate|memory|wiki_entity|wiki_concept)",
            )
    else:
        promotion = None

    handoff_id = fm.get("handoff_id")
    if isinstance(handoff_id, str) and not HANDOFF_ID_RE.match(handoff_id):
        result.error(
            rel,
            f"handoff_id format invalid: {handoff_id!r} "
            f"(expected '<task-slug>:<subject-or-null>:<role>:<NN>')",
        )

    sec = fm.get("security")
    if "security" in fm:
        if not isinstance(sec, dict):
            result.error(rel, "security must be a YAML mapping")
        else:
            if "contains_secrets" not in sec:
                result.error(rel, "security.contains_secrets missing")
            elif not isinstance(sec["contains_secrets"], bool):
                result.error(
                    rel,
                    f"security.contains_secrets must be bool, "
                    f"got {type(sec['contains_secrets']).__name__}",
                )
            if "redaction_status" not in sec:
                result.error(rel, "security.redaction_status missing")
            elif not isinstance(sec["redaction_status"], str):
                result.error(
                    rel,
                    f"security.redaction_status must be string, "
                    f"got {type(sec['redaction_status']).__name__}",
                )

    if isinstance(role, str) and role != role_from_filename:
        result.error(
            rel,
            f"filename role {role_from_filename!r} mismatches "
            f"frontmatter role {role!r}",
        )
    seq = fm.get("handoff_seq")
    if isinstance(seq, int) and seq != seq_from_filename:
        result.error(
            rel,
            f"filename seq {seq_from_filename:02d} mismatches "
            f"frontmatter handoff_seq {seq}",
        )

    contains_secrets, redaction_status = _security_flags(fm)
    if promotion in {"wiki_entity", "wiki_concept"} and contains_secrets is True:
        result.error(
            rel,
            f"promotion={promotion!r} forbidden when "
            f"security.contains_secrets is true",
        )
    if promotion == "memory" and redaction_status == "unchecked":
        result.error(
            rel,
            "promotion='memory' forbidden when "
            "security.redaction_status is 'unchecked'",
        )

    missing_sections = [s for s in CANONICAL_BODY_SECTIONS if s not in body]
    if missing_sections:
        result.warn(
            rel,
            f"missing canonical body sections: {', '.join(missing_sections)}",
        )

    _check_tool_trace_columns(result, rel, body)


def _check_tool_trace_columns(result, rel: str, body: str) -> None:
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
            rel,
            f"tool trace table header has {header.count('|')} pipes, "
            f"expected {TOOL_TRACE_PIPE_COUNT}",
        )


def _validate_final(
    result,
    rel: str,
    final_fm: dict | None,
    sibling_handoffs: list[dict],
) -> None:
    if any(_security_flags(fm)[0] is True for fm in sibling_handoffs):
        result.error(
            rel,
            "final.md forbidden — at least one source handoff has "
            "security.contains_secrets: true",
        )

    if final_fm is None:
        return

    final_contains, _ = _security_flags(final_fm)
    if final_contains is True:
        result.error(rel, "final.md frontmatter has security.contains_secrets: true")


def _validate_readme(
    result,
    rel: str,
    readme_text: str,
    on_disk_handoff_files: set[str],
) -> None:
    section_match = re.search(r"^##\s+Handoff index\b.*$", readme_text, re.MULTILINE)
    if not section_match:
        return
    section_start = section_match.end()
    next_heading = re.search(r"^##\s+", readme_text[section_start:], re.MULTILINE)
    section_end = (
        section_start + next_heading.start() if next_heading else len(readme_text)
    )
    section = readme_text[section_start:section_end]

    listed: set[str] = set()
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("| ---"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        for cell in cells:
            m = re.search(r"([a-z0-9_-]+\.md)", cell)
            if m and m.group(1) != "README.md":
                listed.add(m.group(1))

    for fname in sorted(listed - on_disk_handoff_files):
        result.error(rel, f"Handoff index references missing file: {fname}")
    for fname in sorted(on_disk_handoff_files - listed):
        result.warn(rel, f"on-disk file not in Handoff index: {fname}")
