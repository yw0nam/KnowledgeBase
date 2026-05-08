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

from kb_mcp.cli._handoff_validators import (
    CANONICAL_BODY_SECTIONS as CANONICAL_BODY_SECTIONS,
    FINAL_FILENAME_RE,
    HANDOFF_FILENAME_RE,
    HANDOFF_ID_RE as HANDOFF_ID_RE,
    REQUIRED_FM_KEYS as REQUIRED_FM_KEYS,
    TOOL_TRACE_PIPE_COUNT as TOOL_TRACE_PIPE_COUNT,
    VALID_PROMOTIONS as VALID_PROMOTIONS,
    VALID_ROLES as VALID_ROLES,
    VALID_STATUSES as VALID_STATUSES,
    _check_tool_trace_columns as _check_tool_trace_columns,
    _security_flags as _security_flags,
    _validate_final,
    _validate_handoff,
    _validate_readme,
)

BASEDIR = Path(__file__).resolve().parent.parent.parent.parent
HANDOFFS_DIR = BASEDIR / "data" / "raw" / "handoffs"

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
