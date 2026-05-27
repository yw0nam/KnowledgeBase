"""kb-page CLI: DB-canonical frontmatter authoring + render/import."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml
from sqlalchemy import select

from kb import REPO_ROOT
from kb.cli.page._core import _read_split, ingest_file, render_page_file
from kb.cli.page._serialize import parse_frontmatter, render_block
from kb.db import make_engine, make_session_factory
from kb.db.models import Page


def _data_dir() -> Path:
    return Path(os.environ.get("KB_DATA_DIR", REPO_ROOT / "data")).resolve()


def _wiki_dir(data_dir: Path) -> Path:
    return data_dir / "wiki"


def _iter_wiki_files(wiki_dir: Path) -> list[Path]:
    return [
        p
        for p in sorted(wiki_dir.rglob("*.md"))
        if p.name not in ("_index.md", "INDEX.md")
    ]


def _roundtrip_ok(path: Path) -> bool:
    """True if parsing the file, rendering, and re-parsing yields an equal ParsedPage (the zero-loss roundtrip gate)."""
    fm, _ = _read_split(path)
    parsed = parse_frontmatter(fm)
    rendered = render_block(parsed)
    reparsed = yaml.safe_load(rendered.split("\n", 1)[1]) or {}
    return parse_frontmatter(reparsed) == parsed


def _cmd_import(args: argparse.Namespace) -> int:
    """Ingest wiki frontmatter into the DB and normalize the files.

    Per-page: ``ingest_file`` commits each page individually (via
    ``upsert_page``), so this is NOT one atomic transaction across the whole
    wiki. Recovery from a mid-run failure is to RE-RUN ``import --all`` (the
    upsert-by-stem + idempotent render make it a repair path), not a rollback.
    ``--dry-run`` performs the zero-loss roundtrip gate only and writes nothing.
    """
    data_dir = _data_dir()
    wiki_dir = _wiki_dir(data_dir)
    files = _iter_wiki_files(wiki_dir) if args.all else [Path(args.path).resolve()]

    failures: list[str] = []
    for p in files:
        try:
            if not _roundtrip_ok(p):
                failures.append(f"roundtrip mismatch: {p.relative_to(wiki_dir)}")
        except Exception as exc:  # noqa: BLE001 — report-and-continue gate
            failures.append(f"parse error: {p}: {exc}")
    if failures:
        print("DRY-RUN GATE FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    if args.dry_run:
        print(f"dry-run OK: {len(files)} pages would import")
        return 0

    factory = make_session_factory(make_engine(data_dir))
    session = factory()
    try:
        for p in files:
            ingest_file(session, wiki_dir=wiki_dir, path=p)
    finally:
        session.close()
    print(f"imported {len(files)} pages")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    data_dir = _data_dir()
    wiki_dir = _wiki_dir(data_dir)
    factory = make_session_factory(make_engine(data_dir))
    session = factory()
    try:
        if args.all:
            stems = list(session.execute(select(Page.stem)).scalars().all())
        else:
            stems = [args.stem]
        for stem in stems:
            render_page_file(session, wiki_dir=wiki_dir, stem=stem)
    finally:
        session.close()
    print(f"rendered {len(stems)} pages")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kb-page")
    sub = parser.add_subparsers(dest="cmd", required=True)

    imp = sub.add_parser("import", help="ingest markdown frontmatter into the DB")
    g = imp.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true")
    g.add_argument("path", nargs="?")
    imp.add_argument("--dry-run", action="store_true")
    imp.set_defaults(func=_cmd_import)

    ren = sub.add_parser("render", help="regenerate the frontmatter block from the DB")
    rg = ren.add_mutually_exclusive_group(required=True)
    rg.add_argument("--all", action="store_true")
    rg.add_argument("stem", nargs="?")
    ren.set_defaults(func=_cmd_render)

    args = parser.parse_args(argv)
    return args.func(args)
