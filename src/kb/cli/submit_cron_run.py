"""Submit a cron run log to the KB database (in-process, no HTTP)."""

from __future__ import annotations

import argparse
from pathlib import Path

from kb.service import ops as service_ops
from kb.service.session import session_scope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Submit a cron run log to the KB DB.")
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--status", required=True, choices=["success", "failed"])
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--log-path")
    parser.add_argument("--log-file", type=Path, required=True)
    parser.add_argument("--started-at")
    parser.add_argument("--finished-at")
    args = parser.parse_args(argv)

    with session_scope() as (session, data_dir):
        service_ops.create_cron_run(
            session,
            data_dir,
            job_name=args.job_name,
            target=args.target,
            status=args.status,
            log_body=args.log_file.read_text(encoding="utf-8"),
            exit_code=args.exit_code,
            log_path=args.log_path,
            started_at=args.started_at,
            finished_at=args.finished_at,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
