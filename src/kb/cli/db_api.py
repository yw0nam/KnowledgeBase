"""Small DB-canonical API client for local CLIs and cron wrappers."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

DEFAULT_API_BASE_URL = "http://127.0.0.1:8765/api"


class DbApiError(RuntimeError):
    """Raised when a DB-canonical API request cannot be completed."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def api_base_url() -> str:
    explicit = os.environ.get("KB_API_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    root_url = os.environ.get("KB_API_URL")
    if root_url:
        return f"{root_url.rstrip('/')}/api"
    return DEFAULT_API_BASE_URL


def api_token() -> str:
    token = os.environ.get("KB_API_TOKEN")
    if not token:
        raise DbApiError("KB_API_TOKEN is required for DB-canonical writes")
    return token


def post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{api_base_url()}/{path.lstrip('/')}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_token()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            req, timeout=60
        ) as resp:  # noqa: S310 - local configured API
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise DbApiError(
            f"POST {url} failed: HTTP {exc.code}: {detail}",
            status_code=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        raise DbApiError(f"POST {url} failed: {exc.reason}") from exc


def _split_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    if not markdown.startswith("---\n"):
        raise DbApiError("markdown must start with YAML frontmatter")
    try:
        _, fm_text, body = markdown.split("---", 2)
    except ValueError as exc:
        raise DbApiError("markdown frontmatter closing delimiter is missing") from exc
    frontmatter = yaml.safe_load(fm_text) or {}
    if not isinstance(frontmatter, dict):
        raise DbApiError("markdown frontmatter must be a mapping")
    return frontmatter, body


def markdown_page_payload(
    *,
    markdown: str,
    export_path: str,
    slug: str,
    origin: str,
    source: str,
) -> dict[str, Any]:
    frontmatter, body = _split_frontmatter(markdown)
    page_type = frontmatter.get("type")
    if not isinstance(page_type, str) or not page_type:
        raise DbApiError("page frontmatter requires non-empty type")
    return {
        "slug": slug,
        "type": page_type,
        "title": frontmatter.get("title"),
        "category": frontmatter.get("category"),
        "review_status": frontmatter.get("review_status"),
        "origin": origin,
        "frontmatter": frontmatter,
        "body_md": body,
        "export_path": export_path,
        "source": source,
    }


def _first_heading(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or fallback
    return fallback


def raw_source_payload(
    *,
    markdown: str,
    source_key: str,
    source_type: str | None = None,
) -> dict[str, Any]:
    frontmatter, body = _split_frontmatter(markdown)
    raw_type = source_type or frontmatter.get("type") or "raw"
    return {
        "source_key": source_key,
        "source_type": raw_type,
        "source_url": frontmatter.get("source_url"),
        "title": _first_heading(body, source_key),
        "captured_at": frontmatter.get("captured_at"),
        "frontmatter": frontmatter,
        "content_md": body,
    }


def submit_raw_source(
    *,
    markdown: str,
    source_key: str,
    source_type: str | None = None,
) -> dict[str, Any]:
    return post_json(
        "/raw-sources",
        raw_source_payload(
            markdown=markdown,
            source_key=source_key,
            source_type=source_type,
        ),
    )


def submit_markdown_page(
    *,
    markdown: str,
    export_path: str,
    slug: str,
    origin: str = "ingested",
    source: str = "cli",
) -> dict[str, Any]:
    return post_json(
        "/pages",
        markdown_page_payload(
            markdown=markdown,
            export_path=export_path,
            slug=slug,
            origin=origin,
            source=source,
        ),
    )


def submit_cron_run(
    *,
    job_name: str,
    target: str,
    status: str,
    log_body: str,
    exit_code: int | None = None,
    log_path: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> dict[str, Any]:
    return post_json(
        "/cron-runs",
        {
            "job_name": job_name,
            "target": target,
            "status": status,
            "exit_code": exit_code,
            "log_body": log_body,
            "log_path": log_path,
            "started_at": started_at,
            "finished_at": finished_at,
        },
    )


def submit_metrics(
    *,
    report_date: str,
    report_type: str,
    metrics: dict[str, Any],
    session_count: int | None = None,
    token_total: int | None = None,
    cost_usd: float | None = None,
    tool_error_count: int | None = None,
) -> dict[str, Any]:
    return post_json(
        "/metrics",
        {
            "report_date": report_date,
            "report_type": report_type,
            "session_count": session_count,
            "token_total": token_total,
            "cost_usd": cost_usd,
            "tool_error_count": tool_error_count,
            "metrics_json": metrics,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Submit a cron run log to the KB DB API."
    )
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--status", required=True, choices=["success", "failed"])
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--log-path")
    parser.add_argument("--log-file", type=Path, required=True)
    parser.add_argument("--started-at")
    parser.add_argument("--finished-at")
    args = parser.parse_args(argv)

    submit_cron_run(
        job_name=args.job_name,
        target=args.target,
        status=args.status,
        exit_code=args.exit_code,
        log_path=args.log_path,
        log_body=args.log_file.read_text(encoding="utf-8"),
        started_at=args.started_at,
        finished_at=args.finished_at,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
