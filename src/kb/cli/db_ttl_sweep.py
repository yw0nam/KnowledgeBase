"""Run the DB-canonical wiki TTL sweep."""

from __future__ import annotations

import argparse

from kb.service import pages as service_pages
from kb.service.session import session_scope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args(argv)
    with session_scope() as (session, data_dir):
        result = service_pages.ttl_sweep(session, data_dir, days=args.days)
    print(f"swept: {result.get('swept', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
