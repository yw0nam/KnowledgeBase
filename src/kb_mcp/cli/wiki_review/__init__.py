"""kb-wiki-review CLI — manage review_status lifecycle of wiki pages."""

from __future__ import annotations

import argparse
import datetime
import sys
from zoneinfo import ZoneInfo

from kb_mcp.cli.wiki_review import _commands, _store

KST = ZoneInfo("Asia/Seoul")


def _today_kst() -> str:
    return datetime.datetime.now(KST).date().isoformat()


def _now_iso_kst() -> str:
    return datetime.datetime.now(KST).isoformat(timespec="seconds")


def _read_feedback_interactive() -> str:
    """Read multi-line feedback from stdin until EOF; return stripped text."""
    print("Feedback (empty to skip, Ctrl-D when done):")
    return sys.stdin.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kb-wiki-review",
        description="Manage wiki page approval lifecycle.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List pages by review_status")
    p_list.add_argument(
        "--status",
        default="pending_for_approve",
        choices=["not_processed", "pending_for_approve", "approved", "all"],
    )
    p_list.add_argument(
        "--counts",
        action="store_true",
        help="Print one-line summary instead of listing",
    )

    p_promote = sub.add_parser("promote", help="not_processed → pending_for_approve")
    p_promote.add_argument("stem")

    p_approve = sub.add_parser("approve", help="pending_for_approve → approved")
    p_approve.add_argument("stem")
    p_approve.add_argument(
        "--feedback", default=None, help="Feedback text (omit for interactive prompt)"
    )

    p_reject = sub.add_parser(
        "reject", help="pending_for_approve → rejected (moves file)"
    )
    p_reject.add_argument("stem")
    p_reject.add_argument(
        "--feedback", default=None, help="Feedback text (omit for interactive prompt)"
    )

    p_ttl = sub.add_parser("ttl-sweep", help="Auto-reject stale not_processed pages")
    p_ttl.add_argument(
        "--days", type=int, default=7, help="TTL in days from `created` (default 7)"
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse calls sys.exit() on parse errors / --help. Translate to
        # a return code so main() can be called programmatically (tests).
        code = exc.code if isinstance(exc.code, int) else 2
        return code
    today = _today_kst()
    now = _now_iso_kst()

    if args.cmd == "list":
        return _commands.cmd_list(
            wiki_dir=_store.WIKI_DIR,
            status=args.status,
            counts=args.counts,
            today=today,
        )

    if args.cmd == "promote":
        return _commands.cmd_promote(_store.WIKI_DIR, args.stem)

    if args.cmd == "approve":
        feedback = (
            args.feedback if args.feedback is not None else _read_feedback_interactive()
        )
        return _commands.cmd_approve(
            wiki_dir=_store.WIKI_DIR,
            stem=args.stem,
            feedback=feedback,
            today=today,
            now_iso=now,
        )

    if args.cmd == "reject":
        feedback = (
            args.feedback if args.feedback is not None else _read_feedback_interactive()
        )
        return _commands.cmd_reject(
            wiki_dir=_store.WIKI_DIR,
            rejected_dir=_store.REJECTED_DIR,
            data_dir=_store.WIKI_DIR.parent,
            stem=args.stem,
            feedback=feedback,
            today=today,
            now_iso=now,
            rejected_by="user",
        )

    if args.cmd == "ttl-sweep":
        return _commands.cmd_ttl_sweep(
            wiki_dir=_store.WIKI_DIR,
            rejected_dir=_store.REJECTED_DIR,
            data_dir=_store.WIKI_DIR.parent,
            days=args.days,
            today=today,
            now_iso=now,
        )

    # argparse with required=True should make this unreachable; keep for safety.
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
