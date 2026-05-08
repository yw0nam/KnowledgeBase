#!/usr/bin/env python3
"""Ingest today's HuggingFace Daily Papers email from Gmail into KnowledgeBase raw files.

Default behavior:
- reads the most recent HuggingFace Daily Papers digest from Gmail
- only processes it when the subject paper date equals today's KST date
- extracts paper titles + HuggingFace paper URLs
- fetches each paper abstract from the arXiv API
- writes one immutable markdown source under raw/web/huggingface/
- deduplicates with repo-local state under .kb_state/ingest/daily_papers/

This script intentionally performs INGEST only. The existing kb_update cron/job can
handle graph/fill/lint/log stages separately.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

KB_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = KB_ROOT / "raw" / "web" / "huggingface"
STATE_DIR = KB_ROOT / ".kb_state" / "ingest" / "daily_papers"
GAPI = Path.home() / ".hermes" / "skills" / "productivity" / "google-workspace" / "scripts" / "google_api.py"
GMAIL_QUERY = 'from:daily_papers_digest@notifications.huggingface.co subject:"Daily papers of" newer_than:2d'
KST = timezone(timedelta(hours=9))
ARXIV_API = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"


def run_gapi(*args: str) -> Any:
    """Run Hermes Google Workspace Gmail API wrapper and parse JSON stdout."""
    cmd = [sys.executable, str(GAPI), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=KB_ROOT)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"gapi failed: {' '.join(cmd)}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gapi returned non-JSON output: {proc.stdout[:500]}") from exc


def parse_subject_date(subject: str) -> datetime:
    """Parse subjects like 'Daily papers of 6 May 2026' or 'Daily papers of 30 Apr 2026'."""
    match = re.search(r"Daily papers of\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", subject)
    if not match:
        raise ValueError(f"cannot parse date from subject: {subject}")

    date_text = f"{match.group(1)} {match.group(2)} {match.group(3)}"
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(date_text, fmt)
        except ValueError:
            pass
    raise ValueError(f"cannot parse date from subject: {subject}")


def email_datetime(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def strip_tags(value: str) -> str:
    value = re.sub(r"<span[^>]*>\s*▲\s*</span>", "▲", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(value).strip()


def extract_papers(body: str) -> list[dict[str, str]]:
    """Extract HuggingFace paper links from the digest HTML body."""
    papers: list[dict[str, str]] = []
    seen: set[str] = set()
    pattern = re.compile(
        r'<a\b[^>]*href="(https://huggingface\.co/papers/([^"?]+)[^"]*)"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    for match in pattern.finditer(body):
        url = html.unescape(match.group(1))
        paper_id = match.group(2).strip()
        title = strip_tags(match.group(3))

        if not paper_id or paper_id in seen:
            continue
        if not re.fullmatch(r"\d{4}\.\d+", paper_id):
            continue
        if "utm_source=digest-papers" not in url:
            continue

        title = re.sub(r"\s*\(\d+\s*▲\)\s*$", "", title).strip()
        title = re.sub(r"\s+", " ", title)
        if not title:
            continue

        seen.add(paper_id)
        papers.append(
            {
                "id": paper_id,
                "title": title,
                "url": f"https://huggingface.co/papers/{paper_id}",
                "arxiv_url": f"https://arxiv.org/abs/{paper_id}",
            }
        )
    return papers


def fetch_arxiv_api_abstracts(arxiv_ids: list[str]) -> dict[str, str]:
    """Fetch abstracts for arXiv IDs in one API call."""
    if not arxiv_ids:
        return {}

    query = urllib.parse.urlencode({"id_list": ",".join(arxiv_ids), "max_results": str(len(arxiv_ids))})
    request = urllib.request.Request(
        f"{ARXIV_API}?{query}",
        headers={"User-Agent": "KnowledgeBaseDailyPapers/1.0 (personal ingestion script)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed arXiv endpoint
        xml_text = response.read().decode("utf-8", errors="replace")

    root = ET.fromstring(xml_text)
    abstracts: dict[str, str] = {}
    for entry in root.findall(f"{ATOM}entry"):
        id_text = entry.findtext(f"{ATOM}id", default="")
        summary = entry.findtext(f"{ATOM}summary", default="")
        match = re.search(r"/abs/(\d{4}\.\d+)(?:v\d+)?$", id_text.strip())
        if not match:
            continue
        abstract = re.sub(r"\s+", " ", html.unescape(summary)).strip()
        abstracts[match.group(1)] = abstract
    return abstracts


def fetch_arxiv_page_abstract(arxiv_id: str) -> str:
    """Fallback: scrape the abstract from the public arXiv abs HTML page."""
    request = urllib.request.Request(
        f"https://arxiv.org/abs/{arxiv_id}",
        headers={"User-Agent": "Mozilla/5.0 KnowledgeBaseDailyPapers/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed arXiv endpoint
        page = response.read().decode("utf-8", errors="replace")

    match = re.search(
        r'<blockquote class="abstract[^>]*>\s*<span[^>]*>\s*Abstract:\s*</span>(.*?)</blockquote>',
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    abstract = re.sub(r"<[^>]+>", " ", match.group(1))
    return re.sub(r"\s+", " ", html.unescape(abstract)).strip()


def fetch_arxiv_abstracts(arxiv_ids: list[str]) -> dict[str, str]:
    """Fetch abstracts, with per-paper HTML fallback if the batch API rate-limits."""
    if not arxiv_ids:
        return {}

    try:
        return fetch_arxiv_api_abstracts(arxiv_ids)
    except Exception as exc:  # noqa: BLE001 - fallback should keep cron useful during arXiv API 429s
        print(f"Warning: arXiv API batch fetch failed ({exc}); falling back to arxiv.org/abs pages", file=sys.stderr)

    abstracts: dict[str, str] = {}
    for arxiv_id in arxiv_ids:
        time.sleep(0.75)
        try:
            abstracts[arxiv_id] = fetch_arxiv_page_abstract(arxiv_id)
        except Exception as exc:  # noqa: BLE001 - keep other papers ingesting
            print(f"Warning: abstract fetch failed for {arxiv_id}: {exc}", file=sys.stderr)
            abstracts[arxiv_id] = ""
    return abstracts


def enrich_with_abstracts(papers: list[dict[str, str]]) -> list[dict[str, str]]:
    abstracts = fetch_arxiv_abstracts([paper["id"] for paper in papers])
    for paper in papers:
        paper["abstract"] = abstracts.get(paper["id"], "")
    return papers


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_markdown(email: dict[str, Any], paper_date: datetime, papers: list[dict[str, str]]) -> str:
    subject = email.get("subject", "")
    captured = email_datetime(email.get("date", "")) or datetime.now(timezone.utc)
    paper_date_str = paper_date.strftime("%Y-%m-%d")

    lines = [
        "---",
        f"source_url: {yaml_quote('gmail://' + email['id'])}",
        'type: "web_article"',
        f"captured_at: {yaml_quote(captured.isoformat())}",
        'author: "AK and the AI research community"',
        'contributor: "natsume"',
        "tags:",
        "  - papers",
        "  - arxiv",
        "  - huggingface",
        "  - daily-papers",
        "---",
        "",
        f"# HuggingFace Daily Papers - {paper_date_str}",
        "",
        f"**Email subject:** {subject}",
        f"**Digest date:** {paper_date_str}",
        f"**Gmail message:** `{email['id']}`",
        "**Source:** https://huggingface.co/papers",
        "",
        "## Papers",
        "",
    ]

    for index, paper in enumerate(papers, 1):
        lines.extend(
            [
                f"### {index}. {paper['title']}",
                "",
                f"- HuggingFace: {paper['url']}",
                f"- arXiv: {paper['arxiv_url']}",
                "",
                "**Abstract**",
                "",
                paper.get("abstract") or "_Abstract unavailable from arXiv API._",
                "",
            ]
        )

    return "\n".join(lines)


def ingest(dry_run: bool, force: bool, allow_non_today: bool) -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    emails = run_gapi("gmail", "search", GMAIL_QUERY, "--max", "1")
    if not emails:
        print("No HuggingFace Daily Papers email found.")
        return 0

    email = emails[0]
    paper_date = parse_subject_date(email.get("subject", ""))
    paper_date_str = paper_date.strftime("%Y-%m-%d")
    today_kst = datetime.now(KST).date()

    if not allow_non_today and paper_date.date() != today_kst:
        print(f"Skipping non-today digest: {paper_date_str} (today KST: {today_kst.isoformat()})")
        return 0

    raw_file = RAW_DIR / f"daily_papers_{paper_date_str}.md"
    marker = STATE_DIR / f"{paper_date_str}.json"

    if not force and (raw_file.exists() or marker.exists()):
        print(f"Skipping already ingested digest: {paper_date_str}")
        return 0

    message = run_gapi("gmail", "get", email["id"])
    papers = extract_papers(message.get("body", ""))
    if not papers:
        raise RuntimeError(f"No papers extracted from Gmail message {email['id']} ({email.get('subject')})")
    papers = enrich_with_abstracts(papers)

    content = render_markdown(email, paper_date, papers)
    if dry_run:
        print(f"DRY RUN: would write {raw_file} with {len(papers)} papers")
        print(content[:4000])
        return 0

    raw_file.write_text(content, encoding="utf-8")
    marker.write_text(
        json.dumps(
            {
                "paper_date": paper_date_str,
                "gmail_message_id": email["id"],
                "raw_file": str(raw_file.relative_to(KB_ROOT)),
                "paper_count": len(papers),
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {raw_file.relative_to(KB_ROOT)} ({len(papers)} papers with abstracts)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="fetch and parse, but do not write files")
    parser.add_argument("--force", action="store_true", help="overwrite even if the digest was already ingested")
    parser.add_argument(
        "--allow-non-today",
        action="store_true",
        help="manual/testing escape hatch; default cron behavior only processes today's KST subject date",
    )
    args = parser.parse_args()

    try:
        return ingest(dry_run=args.dry_run, force=args.force, allow_non_today=args.allow_non_today)
    except Exception as exc:  # noqa: BLE001 - script should print clear cron errors
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
