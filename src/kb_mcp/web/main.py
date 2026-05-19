"""Entrypoint for the `kb-web` console script.

Starts uvicorn programmatically using KB_WEB_HOST / KB_WEB_PORT (see
`kb_mcp.web.config`). Reload is on in development; production is out
of scope for now per the local-only posture.
"""

from __future__ import annotations

import argparse

import uvicorn

from kb_mcp.web import config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kb-web",
        description="Run the local review console API server.",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Restart on source change (dev only).",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Override KB_WEB_HOST.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Override KB_WEB_PORT.",
    )
    args = parser.parse_args(argv)

    cfg = config.load()
    host = args.host or cfg.host
    port = args.port or cfg.port

    uvicorn.run(
        "kb_mcp.web.app:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
