"""Handoff system linter — validate frontmatter, security flags, and naming.

Scans data/raw/handoffs/<YYYY>/<MM>/<task-slug>/*.md for:
  - Required frontmatter fields (handoff_id, task_slug, role, status, ...)
  - Enum values (role, status, promotion)
  - handoff_id format <task-slug>:<subject-or-null>:<role>:<NN>
  - Filename ↔ role/seq consistency
  - Security ERRORs (contains_secrets bleed-through into final/promotion)
  - Task README handoff index ↔ on-disk file consistency

Usage:
    uv run python -m kb_mcp.cli.lint_handoff           # full lint
    uv run python -m kb_mcp.cli.lint_handoff --strict  # warnings → errors

Exit code: 0 if no errors (or --strict and no warnings), 1 otherwise.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import yaml

BASEDIR = Path(__file__).resolve().parent.parent.parent.parent
HANDOFFS_DIR = BASEDIR / "data" / "raw" / "handoffs"

VALID_ROLES = {
    "main_gateway",
    "research",
    "structuring",
    "execution",
    "verification",
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
    r"(?:main_gateway|research|structuring|execution|verification):\d{2}$"
)

HANDOFF_FILENAME_RE = re.compile(
    r"^(?:(?P<subject>[a-z0-9-]+)_)?"
    r"(?P<role>main_gateway|research|structuring|execution|verification)"
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


class LintResult:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, file: str, msg: str) -> None:
        self.errors.append(f"  ERROR   {file}: {msg}")

    def warn(self, file: str, msg: str) -> None:
        self.warnings.append(f"  WARN    {file}: {msg}")

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def print_report(self) -> None:
        total = len(self.errors) + len(self.warnings)
        if total == 0:
            print("All checks passed.")
            return

        if self.errors:
            print(f"\n--- Errors ({len(self.errors)}) ---\n")
            for e in sorted(self.errors):
                print(e)

        if self.warnings:
            print(f"\n--- Warnings ({len(self.warnings)}) ---\n")
            for w in sorted(self.warnings):
                print(w)

        print("\n--- Summary ---\n")
        print(f"  Errors:   {len(self.errors)}")
        print(f"  Warnings: {len(self.warnings)}")


def _parse_frontmatter(text: str) -> tuple[dict | None, str]:
    if not text.startswith("---"):
        return None, "missing frontmatter (no leading '---')"
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, "malformed frontmatter (missing closing '---')"
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        return None, f"YAML parse error: {exc}"
    if fm is None:
        return {}, ""
    if not isinstance(fm, dict):
        return None, "frontmatter must be a YAML mapping"
    return fm, ""


def _body_after_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    return parts[2] if len(parts) >= 3 else ""


def _iter_task_dirs(handoffs_dir: Path) -> Iterator[Path]:
    for year_dir in sorted(p for p in handoffs_dir.iterdir() if p.is_dir()):
        if not re.fullmatch(r"\d{4}", year_dir.name):
            continue
        for month_dir in sorted(p for p in year_dir.iterdir() if p.is_dir()):
            if not re.fullmatch(r"\d{2}", month_dir.name):
                continue
            for task_dir in sorted(p for p in month_dir.iterdir() if p.is_dir()):
                yield task_dir


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
    result: LintResult,
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
    if "role" in fm and role not in VALID_ROLES:
        result.error(
            rel,
            f"invalid role: {role!r} (must be one of {sorted(VALID_ROLES)})",
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

    if role in VALID_ROLES and role != role_from_filename:
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


def _check_tool_trace_columns(result: LintResult, rel: str, body: str) -> None:
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
    result: LintResult,
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
    result: LintResult,
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


def _lint_task(result: LintResult, task_dir: Path, handoffs_dir: Path) -> None:
    handoff_fms: list[dict] = []
    final_paths: list[tuple[Path, dict | None]] = []
    readme_path: Path | None = None
    on_disk_handoff_files: set[str] = set()

    for md in sorted(task_dir.glob("*.md")):
        rel = str(md.relative_to(handoffs_dir))
        text = md.read_text()
        fm, fm_err = _parse_frontmatter(text)
        body = _body_after_frontmatter(text)

        if md.name == "README.md":
            readme_path = md
            continue

        if fm is None:
            result.error(rel, fm_err)
            continue

        final_match = FINAL_FILENAME_RE.match(md.name)
        handoff_match = HANDOFF_FILENAME_RE.match(md.name)

        if final_match:
            final_paths.append((md, fm))
            continue

        if not handoff_match:
            result.warn(
                rel,
                f"unrecognized filename pattern: {md.name!r} "
                f"(expected '[<subject>_]<role>_handoff_<NN>.md' or "
                f"'<slug>_final.md')",
            )
            continue

        on_disk_handoff_files.add(md.name)
        role_from_filename = handoff_match.group("role")
        seq_from_filename = int(handoff_match.group("seq"))
        _validate_handoff(
            result,
            rel,
            fm,
            role_from_filename=role_from_filename,
            seq_from_filename=seq_from_filename,
            body=body,
        )
        handoff_fms.append(fm)

    for final_path, final_fm in final_paths:
        rel = str(final_path.relative_to(handoffs_dir))
        _validate_final(result, rel, final_fm, handoff_fms)

    if readme_path is not None:
        rel = str(readme_path.relative_to(handoffs_dir))
        _validate_readme(
            result,
            rel,
            readme_path.read_text(),
            on_disk_handoff_files,
        )


def lint(result: LintResult, handoffs_dir: Path | None = None) -> None:
    """Walk handoff task directories and populate ``result`` with findings."""
    handoffs_dir = handoffs_dir if handoffs_dir is not None else HANDOFFS_DIR
    if not handoffs_dir.exists():
        return
    for task_dir in _iter_task_dirs(handoffs_dir):
        _lint_task(result, task_dir, handoffs_dir)


def main() -> None:
    parser = argparse.ArgumentParser(prog="kb-lint-handoff", description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings as errors (exit 1 on any warning)",
    )
    args = parser.parse_args()

    print("Linting data/raw/handoffs/...\n")

    result = LintResult()
    lint(result)
    result.print_report()

    if not result.ok:
        print("\nFAILED — fix errors before committing.")
        sys.exit(1)
    if args.strict and result.warnings:
        print("\nFAILED (--strict) — warnings treated as errors.")
        sys.exit(1)
    print("\nPASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
