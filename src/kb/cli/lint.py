"""DB-backed lint CLI.

Usage:
    kb-lint wiki      # Full wiki scan (cross-page validation)
    kb-lint handoff   # Handoff validation
    kb-lint all       # Both

Exit 0 if no errors, 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys

from kb.db import make_engine, make_session_factory
from kb.lint.common import LintResult
from kb.lint.wiki import validate_page_full
from kb.lint.handoff import validate_handoff_create
from kb.db.models import Handoff


def _exit_code(results: list[LintResult], strict: bool) -> int:
    """Resolve the process exit code from lint results.

    Errors always fail. Under ``--strict``, warnings fail too.
    """
    if any(r.errors for r in results):
        return 1
    if strict and any(r.warnings for r in results):
        return 1
    return 0


def _print_report(result, label: str) -> bool:
    print(f"\n--- {label} ---")
    total = len(result.errors) + len(result.warnings)
    if total == 0:
        print("  All checks passed.")
        return True
    if result.errors:
        for e in sorted(result.errors):
            print(e)
    if result.warnings:
        for w in sorted(result.warnings):
            print(w)
    print(f"\n  Errors:   {len(result.errors)}")
    print(f"  Warnings: {len(result.warnings)}")
    return result.ok


def cmd_wiki(session) -> LintResult:
    print("Linting wiki pages (DB-backed)...")
    result = validate_page_full(session)
    _print_report(result, "Wiki")
    return result


def cmd_handoff(session) -> LintResult:
    print("Linting handoffs (DB-backed)...")
    result = LintResult()
    handoffs = list(session.query(Handoff).all())
    if not handoffs:
        print("  No handoffs found.")
        return result
    for h in handoffs:
        r = validate_handoff_create(h.frontmatter, h.body_md)
        result.errors.extend(r.errors)
        result.warnings.extend(r.warnings)
    _print_report(result, "Handoffs")
    return result


def main():
    parser = argparse.ArgumentParser(
        prog="kb-lint", description="DB-backed KnowledgeBase lint"
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="all",
        choices=["wiki", "handoff", "all"],
        help="Lint target (default: all)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors",
    )
    args = parser.parse_args()

    engine = make_engine()
    session_factory = make_session_factory(engine)
    session = session_factory()

    results: list[LintResult] = []
    try:
        if args.target in ("wiki", "all"):
            results.append(cmd_wiki(session))
        if args.target in ("handoff", "all"):
            results.append(cmd_handoff(session))
    finally:
        session.close()

    code = _exit_code(results, args.strict)
    if code != 0:
        if any(r.errors for r in results):
            print("\nFAILED — fix errors before committing.")
        else:
            print("\nFAILED (--strict) — warnings treated as errors.")
    else:
        print("\nPASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
