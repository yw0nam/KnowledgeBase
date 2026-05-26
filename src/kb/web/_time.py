"""KST (Asia/Seoul) timestamp helpers shared by route modules."""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now_iso_kst() -> str:
    """Return current KST time as ``YYYY-MM-DDTHH:MM:SS+09:00``.

    The format matches the SQL CHECK constraints on
    ``dispatches.*_at`` and ``wiki_edits.edited_at``.
    """
    return datetime.datetime.now(KST).isoformat(timespec="seconds")


def today_kst() -> str:
    """Return today's date in KST as ``YYYY-MM-DD``."""
    return datetime.datetime.now(KST).date().isoformat()
