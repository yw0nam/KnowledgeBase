"""Run the DB-canonical wiki TTL sweep."""

from __future__ import annotations

import argparse

from kb.cli.db_api import post_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args(argv)
    response = post_json(f"/pages/ttl-sweep?days={args.days}", {})
    print(f"swept: {response.get('swept', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
