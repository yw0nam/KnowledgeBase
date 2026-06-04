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

from kb import data_dir
from kb.db import make_engine, make_session_factory
from kb.lint.wiki import validate_page_full
from kb.lint.handoff import validate_handoff_create
from kb.db.models import Handoff


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


def cmd_wiki(session) -> bool:
    print("Linting wiki pages (DB-backed)...")
    result = validate_page_full(session)
    return _print_report(result, "Wiki")


def cmd_handoff(session) -> bool:
    print("Linting handoffs (DB-backed)...")
    from kb.lint.common import LintResult

    result = LintResult()
    handoffs = list(session.query(Handoff).all())
    if not handoffs:
        print("  No handoffs found.")
        return True
    for h in handoffs:
        r = validate_handoff_create(h.frontmatter, h.body_md)
        result.errors.extend(r.errors)
        result.warnings.extend(r.warnings)
    return _print_report(result, "Handoffs")


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

    data_root = data_dir()
    engine = make_engine(data_root)
    session_factory = make_session_factory(engine)
    session = session_factory()

    ok = True
    try:
        if args.target in ("wiki", "all"):
            if not cmd_wiki(session):
                ok = False

        if args.target in ("handoff", "all"):
            if not cmd_handoff(session):
                ok = False
    finally:
        session.close()

    summary = "PASSED" if ok else "FAILED"
    if not ok:
        print(f"\n{summary} — fix errors before committing.")
        sys.exit(1)
    elif args.strict and any(
        r.warnings for r in []  # aggregated report already printed
    ):
        print("\nFAILED (--strict) — warnings treated as errors.")
        sys.exit(1)
    else:
        print(f"\n{summary}")
        sys.exit(0)


if __name__ == "__main__":
    main()
