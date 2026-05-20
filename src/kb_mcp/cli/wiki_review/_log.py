"""Append-only daily log writer for kb-wiki-review actions.

``data/log.md`` is the project's append-only operation record. Cron
memory workflows already write to it with their own entries; this
module appends a single bulleted line per wiki-review action so the
file remains a grep-able audit trail of every promote, approve, and
reject the operator (or ttl-sweep) executes.

Format::

    ## 2026-05-19
    - promote: foo-concept (concept)
    - approve: bar-entity (entity)
    - reject: baz-question (question, user)

Today's H2 heading is created lazily; other producers' entries under
the same heading are left untouched. I/O failures are swallowed — the
audit log is best-effort and must never block the user's action.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TAIL_PROBE_BYTES = 2048


def append_action(
    log_path: Path,
    today: str,
    action: str,
    stem: str,
    page_type: str = "",
    note: str = "",
) -> None:
    """Append one entry under today's H2 heading in ``log_path``.

    ``page_type`` and ``note`` are optional metadata bits appended in
    parentheses, comma-separated, when present.
    """
    try:
        tail = ""
        if log_path.is_file():
            with log_path.open("rb") as fh:
                size = log_path.stat().st_size
                if size > _TAIL_PROBE_BYTES:
                    fh.seek(-_TAIL_PROBE_BYTES, 2)
                tail = fh.read().decode("utf-8", errors="replace")
        needs_heading = f"## {today}" not in tail
        meta_bits = [b for b in (page_type, note) if b]
        meta = f" ({', '.join(meta_bits)})" if meta_bits else ""
        with log_path.open("a", encoding="utf-8") as fh:
            if needs_heading:
                if tail and not tail.endswith("\n"):
                    fh.write("\n")
                if tail:
                    fh.write("\n")
                fh.write(f"## {today}\n")
            fh.write(f"- {action}: {stem}{meta}\n")
    except OSError as exc:
        print(f"warning: log write failed ({log_path}): {exc}", file=sys.stderr)
