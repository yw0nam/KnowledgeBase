"""Secondary wiki lint checks."""

from __future__ import annotations

import datetime
import re
import subprocess
from pathlib import Path

from kb_mcp.cli._wiki_utils import _find_relative, _parse_yaml_frontmatter, extract_links

BASEDIR = Path(__file__).resolve().parent.parent.parent.parent
WIKI_DIR = BASEDIR / "data" / "wiki"
RAW_DIR = BASEDIR / "data" / "raw"

# ── Raw frontmatter contract (per CLAUDE.md "Raw files" section) ────
RAW_FM_REQUIRED = ("source_url", "type", "captured_at", "contributor")
# Raw subdirectories that hold ingested external sources and therefore must
# satisfy the standard raw frontmatter contract. Other top-level dirs
# (handoffs/, ops/, sessions/) follow specialized templates handled
# elsewhere (kb-lint-handoff) and are skipped here.
RAW_INGEST_TOPLEVEL = frozenset(
    {"github", "gmail", "calendar", "web", "manual", "conversations"}
)
# Tolerance for mtime > captured_at (seconds). Allows for normal capture →
# write delay (clock skew, fs latency) without flagging genuine immutability
# violations. 60s is enough for any sane ingest pipeline.
CAPTURED_AT_MTIME_TOLERANCE_SEC = 60


def check_index_sync(result, wiki_dir: Path = None) -> None:
    """Verify that each subject's _index.md lists exactly the pages that exist on disk.

    For every entities/{subject}/_index.md:
      - listed_but_missing → ERROR (broken hub)
      - on_disk_not_listed → WARN  (page exists but not advertised in the hub)

    Scope constraint: wikilinks are extracted ONLY from the ``## Pages``
    section, after fenced code blocks (``` ... ``` and ~~~ ... ~~~) are
    stripped. Links elsewhere in the hub body (notes, references, prompt
    templates) are intentionally ignored to avoid false positives. If the hub
    has no ``## Pages`` heading, the sync check is skipped entirely for that
    hub — empty/template hubs shouldn't flood the output.
    """
    wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR
    entities_root = wiki_dir / "entities"
    if not entities_root.exists():
        return

    for index_file in entities_root.rglob("_index.md"):
        subject_dir = index_file.parent
        subject = subject_dir.name
        rel_index = str(index_file.relative_to(wiki_dir))

        raw_text = index_file.read_text()

        # Strip fenced code blocks so wikilinks inside templates / examples
        # are not mistaken for hub entries.
        stripped = re.sub(r"```.*?```", "", raw_text, flags=re.DOTALL)
        stripped = re.sub(r"~~~.*?~~~", "", stripped, flags=re.DOTALL)

        # Limit scope to the ## Pages section (heading inclusive, up to the
        # next ## heading or EOF). If the hub has no Pages heading at all,
        # skip sync entirely.
        pages_match = re.search(r"^##\s+Pages\b.*$", stripped, re.MULTILINE)
        if not pages_match:
            continue

        section_start = pages_match.end()
        next_heading = re.search(r"^##\s+", stripped[section_start:], re.MULTILINE)
        section_end = (
            section_start + next_heading.start() if next_heading else len(stripped)
        )
        pages_section = stripped[section_start:section_end]

        listed_stems = set(extract_links(pages_section))

        on_disk_stems = {
            f.stem for f in subject_dir.rglob("*.md") if f.stem != "_index"
        }

        # Filter wikilinks to only those that look like they target a subject
        # page (no "/" in the link → simple stem reference).
        # Also drop self-link to _index.
        listed_stems = {
            link for link in listed_stems if "/" not in link and link != "_index"
        }

        listed_but_missing = listed_stems - on_disk_stems
        on_disk_not_listed = on_disk_stems - listed_stems

        for stem in sorted(listed_but_missing):
            result.error(
                rel_index,
                f"_index.md lists [[{stem}]] but no file with that stem under {subject_dir.relative_to(wiki_dir)}",
            )

        for stem in sorted(on_disk_not_listed):
            page_rel = _find_relative(stem, wiki_dir)
            result.warn(
                page_rel,
                f"page not listed in {subject}/_index.md",
            )


def _get_modified_raw_files(data_dir: Path) -> set[Path] | None:
    """Return modified-but-not-newly-added paths under ``raw/`` per ``git status``.

    Returns ``None`` (skip silently) when:
      - ``data_dir/.git`` is missing — no immutability gate possible
      - ``git`` binary not on PATH (``FileNotFoundError``)
      - ``git status`` times out (``subprocess.TimeoutExpired``)
      - ``git status`` exits non-zero

    Otherwise parses porcelain output. ``git status --porcelain`` emits two
    status columns ``XY`` followed by a path. Untracked (``??``) and any
    line whose index column is ``A`` (newly added: ``A `` or ``AM``) are
    treated as NEW files and skipped — immutability only applies to files
    that were committed and then changed. Anything else with ``M`` or ``D``
    in either column is reported as a violation.
    """
    if not (data_dir / ".git").exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", str(data_dir), "status", "--porcelain", "raw/"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None

    modified: set[Path] = set()
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        x, y, rest = line[0], line[1], line[3:]
        # Strip rename-target arrows (``orig -> new``) — we only care about
        # the destination path.
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        # Git quotes paths containing special chars; strip surrounding quotes.
        if rest.startswith('"') and rest.endswith('"'):
            rest = rest[1:-1]

        # Untracked or freshly added → not an immutability violation.
        if x == "?" and y == "?":
            continue
        if x == "A":
            continue
        # Anything with M/D in either column is a real change to a tracked file.
        if "M" in (x, y) or "D" in (x, y):
            modified.add(data_dir / rest)
    return modified


def check_raw_frontmatter(result, raw_dir: Path = None) -> None:
    """Every raw ingest file must declare the standard frontmatter contract.

    Iterates ``*.md`` under ``raw_dir`` but limits checks to the ingest
    categories declared in ``RAW_INGEST_TOPLEVEL``; ``handoffs/``, ``ops/``,
    and ``sessions/`` use specialized templates and are linted by
    ``kb-lint-handoff``. ``README.md`` files are documentation and skipped.
    """
    raw_dir = raw_dir if raw_dir is not None else RAW_DIR
    if not raw_dir.exists():
        return
    for f in raw_dir.rglob("*.md"):
        rel = f.relative_to(raw_dir)
        if not rel.parts or rel.parts[0] not in RAW_INGEST_TOPLEVEL:
            continue
        if f.name == "README.md":
            continue
        fm = _parse_yaml_frontmatter(f.read_text())
        rel_str = f"raw/{rel.as_posix()}"
        if fm is None:
            result.error(rel_str, "missing or invalid frontmatter")
            continue
        for key in RAW_FM_REQUIRED:
            if key not in fm:
                result.error(rel_str, f"raw frontmatter missing required field: {key}")


def check_raw_captured_at_mtime(result, raw_dir: Path = None) -> None:
    """Flag files whose mtime drifts past ``captured_at`` beyond tolerance.

    Raw files are immutable; once captured, the on-disk mtime should not
    advance past the declared ``captured_at`` timestamp. A small tolerance
    (``CAPTURED_AT_MTIME_TOLERANCE_SEC``) absorbs normal capture→write
    latency. Parsing failures are silent here — those are caught by
    ``check_raw_frontmatter``.
    """
    raw_dir = raw_dir if raw_dir is not None else RAW_DIR
    if not raw_dir.exists():
        return
    for f in raw_dir.rglob("*.md"):
        rel = f.relative_to(raw_dir)
        if not rel.parts or rel.parts[0] not in RAW_INGEST_TOPLEVEL:
            continue
        if f.name == "README.md":
            continue
        fm = _parse_yaml_frontmatter(f.read_text())
        if fm is None:
            continue
        captured_at = fm.get("captured_at")
        if captured_at in (None, ""):
            continue

        captured_ts: float
        try:
            if isinstance(captured_at, datetime.datetime):
                dt = captured_at
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                captured_ts = dt.timestamp()
            elif isinstance(captured_at, datetime.date):
                dt = datetime.datetime(
                    captured_at.year,
                    captured_at.month,
                    captured_at.day,
                    tzinfo=datetime.timezone.utc,
                )
                captured_ts = dt.timestamp()
            else:
                s = str(captured_at).strip()
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                dt = datetime.datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                captured_ts = dt.timestamp()
        except (ValueError, TypeError):
            continue

        mtime = f.stat().st_mtime
        if mtime > captured_ts + CAPTURED_AT_MTIME_TOLERANCE_SEC:
            delta = int(mtime - captured_ts)
            result.error(
                f"raw/{rel.as_posix()}",
                f"mtime is {delta}s after captured_at (tolerance "
                f"{CAPTURED_AT_MTIME_TOLERANCE_SEC}s) — raw files must be immutable",
            )


def check_raw_immutability(
    result, raw_dir: Path = None, data_dir: Path = None
) -> None:
    """Reject any raw file modified after its initial commit.

    Uses ``_get_modified_raw_files`` to read git's view of the working
    tree. Files that are merely untracked or freshly added are not flagged
    — only previously-committed paths that have since been modified or
    deleted. When git is unavailable the check is silently skipped.
    """
    raw_dir = raw_dir if raw_dir is not None else RAW_DIR
    data_dir = data_dir if data_dir is not None else raw_dir.parent
    modified = _get_modified_raw_files(data_dir)
    if modified is None:
        return
    for path in modified:
        try:
            rel = path.relative_to(raw_dir)
        except ValueError:
            continue
        result.error(
            f"raw/{rel.as_posix()}",
            "raw file modified after creation (immutability violation)",
        )
