"""Frontmatter/body validators for wiki linting."""

from __future__ import annotations

import re
from pathlib import Path

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
IMPROVEMENT_KIND_VALUES = frozenset({"improvement", "issue", "proposal"})
IMPROVEMENT_DOMAIN_VALUES = frozenset({"cost", "correctness", "perf", "dx", "security"})
IMPROVEMENT_SEVERITY_VALUES = frozenset({"low", "med", "high"})
IMPROVEMENT_STATUS_VALUES = frozenset({"open", "acknowledged", "resolved", "wontfix"})


def _validate_improvement_fm(
    rel: str,
    fm: dict,
    result,
    all_stems: set[str],
    wiki_dir: Path,
) -> None:
    """Enum + reference validation for ``type: improvement`` pages."""
    kind = fm.get("kind")
    if kind not in (None, "") and kind not in IMPROVEMENT_KIND_VALUES:
        result.error(
            rel,
            f"invalid kind: {kind!r} (must be one of {sorted(IMPROVEMENT_KIND_VALUES)})",
        )

    observed_at = fm.get("observed_at")
    if observed_at not in (None, "") and not ISO_DATE_RE.match(str(observed_at)):
        result.error(
            rel,
            f"observed_at must be ISO date YYYY-MM-DD, got {observed_at!r}",
        )

    domain = fm.get("domain")
    if domain not in (None, "") and domain not in IMPROVEMENT_DOMAIN_VALUES:
        result.error(
            rel,
            f"invalid domain: {domain!r} (must be one of {sorted(IMPROVEMENT_DOMAIN_VALUES)})",
        )

    severity = fm.get("severity")
    if severity not in (None, "") and severity not in IMPROVEMENT_SEVERITY_VALUES:
        result.error(
            rel,
            f"invalid severity: {severity!r} (must be one of {sorted(IMPROVEMENT_SEVERITY_VALUES)})",
        )

    status = fm.get("status")
    if status not in (None, "") and status not in IMPROVEMENT_STATUS_VALUES:
        result.error(
            rel,
            f"invalid status: {status!r} (must be one of {sorted(IMPROVEMENT_STATUS_VALUES)})",
        )

    related = fm.get("related", [])
    if isinstance(related, list):
        for ref in related:
            if not isinstance(ref, str) or not ref:
                continue
            if "/" in ref:
                if not (wiki_dir / ref).exists():
                    result.error(rel, f"related: target not found: {ref}")
            else:
                stem = ref[:-3] if ref.endswith(".md") else ref
                if stem not in all_stems:
                    result.error(rel, f"related: target not found: {ref}")


def _validate_checklist_items(rel: str, body: str, result) -> None:
    """All bullets under ``## Items`` must use markdown task-list syntax."""
    m = re.search(r"^##\s+Items\b.*$", body, re.MULTILINE)
    if not m:
        return
    section_start = m.end()
    next_h = re.search(r"^##\s+", body[section_start:], re.MULTILINE)
    section_end = section_start + next_h.start() if next_h else len(body)
    section = body[section_start:section_end]

    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        if not re.match(r"^- \[[ xX]\]\s", stripped):
            preview = stripped[:60]
            result.error(rel, f"checklist item not in task-list syntax: {preview!r}")
