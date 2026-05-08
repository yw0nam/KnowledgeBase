#!/usr/bin/env python3
"""
Wiki linter — health check for the KnowledgeBase vault.

Checks:
  1. Dead wikilinks (link target doesn't exist)
  2. .md extension in wikilink targets (Obsidian doesn't need it)
  3. Self-referencing links
  4. LaTeX/HTML in content (Obsidian markdown only)
  5. Unfilled LLM placeholders (<!-- LLM TODO: -->)
  6. Frontmatter format (missing/invalid, quoted types, inline sources,
     missing/unknown type, missing required fields)
  7. Empty () in Relationships section
  8. Empty sections (heading with no content before next heading)
  9. Stale sources (sources reference non-existent raw files)
 10. Stub pages (body length below STUB_THRESHOLD_CHARS)
 11. Orphan pages (no inbound links from other wiki pages)
 12. Subject _index.md ↔ disk sync (listed pages exist, on-disk pages listed)
 13. Improvement enum validation (kind, observed_at, domain, severity, status,
     related path resolution)
 14. Checklist items must use markdown task-list syntax under ``## Items``
 15. Raw frontmatter required fields (source_url, type, captured_at,
     contributor) — always-on, scoped to raw ingest categories
 16. Raw immutability — ``--check-immutability`` opts in to:
       a) git-status modified-but-not-new files under data/raw/ → ERROR
       b) file mtime later than captured_at by more than the tolerance → ERROR

Usage:
    uv run python -m kb_mcp.cli.lint_wiki                       # full lint
    uv run python -m kb_mcp.cli.lint_wiki --strict              # warnings → errors + immutability on
    uv run python -m kb_mcp.cli.lint_wiki --check-immutability  # immutability checks only
"""

from __future__ import annotations

import datetime
import re
import subprocess
import sys
from pathlib import Path

import yaml

BASEDIR = Path(__file__).resolve().parent.parent.parent.parent
WIKI_DIR = BASEDIR / "data" / "wiki"
RAW_DIR = BASEDIR / "data" / "raw"

# Body length (after frontmatter) below this is flagged as a stub page.
STUB_THRESHOLD_CHARS = 100

# ── Improvement enum vocabularies (per spec lines 432-444) ──────────
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
IMPROVEMENT_KIND_VALUES = frozenset({"improvement", "issue", "proposal"})
IMPROVEMENT_DOMAIN_VALUES = frozenset({"cost", "correctness", "perf", "dx", "security"})
IMPROVEMENT_SEVERITY_VALUES = frozenset({"low", "med", "high"})
IMPROVEMENT_STATUS_VALUES = frozenset({"open", "acknowledged", "resolved", "wontfix"})

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

REQUIRED_FM_FIELDS = {
    "entity": ["type", "created", "updated", "sources", "tags"],
    "concept": ["type", "created", "updated", "sources", "tags"],
    "decision": ["type", "created", "updated", "sources", "tags"],
    # Improvement adds the lifecycle/severity/domain triplet plus
    # observation timestamp and back-references; enums are checked by
    # ``_validate_improvement_fm`` after the required-field loop.
    "improvement": [
        "type",
        "kind",
        "observed_at",
        "domain",
        "severity",
        "status",
        "related",
        "created",
        "updated",
        "sources",
        "tags",
    ],
    "checklist": ["type", "created", "updated", "sources", "tags"],
    "summary": ["type", "created", "updated", "sources", "tags"],
    "question": ["type", "created", "updated", "sources", "tags"],
    "index": ["type", "created", "updated"],
}

COLLISION_EXEMPT_STEMS = frozenset({"_index"})


class LintResult:
    def __init__(self):
        self.errors: list[str] = []  # must fix
        self.warnings: list[str] = []  # should fix

    def error(self, file: str, msg: str):
        self.errors.append(f"  ERROR   {file}: {msg}")

    def warn(self, file: str, msg: str):
        self.warnings.append(f"  WARN    {file}: {msg}")

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def print_report(self):
        total = len(self.errors) + len(self.warnings)
        if total == 0:
            print("All checks passed.")
            return

        if self.errors:
            print(f"\n--- Errors ({len(self.errors)}) ---\n")
            for e in sorted(self.errors):
                print(e)

        if self.warnings:
            print(f"\n--- Warnings ({len(self.warnings)}) ---\n")
            for w in sorted(self.warnings):
                print(w)

        print("\n--- Summary ---\n")
        print(f"  Errors:   {len(self.errors)}")
        print(f"  Warnings: {len(self.warnings)}")


def parse_frontmatter(content: str) -> dict | None:
    """Extract frontmatter fields from markdown content (no yaml dependency)."""
    if not content.startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    fm_text = parts[1].strip()
    if not fm_text:
        return {}
    result = {}
    current_key = None
    current_list = None
    for line in fm_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        # List item under current key
        if stripped.startswith("- ") and current_key:
            if current_list is None:
                current_list = []
                result[current_key] = current_list
            current_list.append(stripped[2:].strip().strip('"').strip("'"))
            continue
        # Key: value
        m = re.match(r"^([a-zA-Z_]+)\s*:\s*(.*)", stripped)
        if m:
            current_key = m.group(1)
            val = m.group(2).strip()
            current_list = None
            if val == "" or val == "[]":
                result[current_key] = []
            elif val.startswith("["):
                # Inline list
                items = val.strip("[]").split(",")
                result[current_key] = [
                    i.strip().strip('"').strip("'") for i in items if i.strip()
                ]
            elif val.startswith('"') or val.startswith("'"):
                result[current_key] = val.strip('"').strip("'")
            else:
                result[current_key] = val
    return result


def get_raw_frontmatter(content: str) -> str:
    """Get raw frontmatter string for format checks."""
    if not content.startswith("---"):
        return ""
    parts = content.split("---", 2)
    return parts[1] if len(parts) >= 3 else ""


def _parse_yaml_frontmatter(text: str) -> dict | None:
    """Parse raw-file frontmatter via PyYAML. Returns None on absent/invalid."""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    return fm if isinstance(fm, dict) else None


def collect_pages(
    wiki_dir: Path = None,
) -> tuple[dict[str, str], dict[str, list[Path]]]:
    """Return ``(pages, paths_by_stem)``: stem→content for one of the
    colliding files (Obsidian wikilinks resolve by stem alone, so the
    dict cannot hold both), and stem→every path sharing the stem so
    the lint pass can flag collisions the stem-keyed dict cannot
    represent."""
    wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR
    pages: dict[str, str] = {}
    paths_by_stem: dict[str, list[Path]] = {}
    for f in wiki_dir.rglob("*.md"):
        paths_by_stem.setdefault(f.stem, []).append(f)
        if f.stem not in pages:
            pages[f.stem] = f.read_text()
    return pages, paths_by_stem


def extract_links(content: str) -> list[str]:
    """Extract wikilink targets from content."""
    return re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", content)


def _validate_improvement_fm(
    rel: str,
    fm: dict,
    result: LintResult,
    all_stems: set[str],
    wiki_dir: Path,
) -> None:
    """Enum + reference validation for ``type: improvement`` pages."""
    kind = fm.get("kind")
    if kind not in (None, "") and kind not in IMPROVEMENT_KIND_VALUES:
        result.error(
            rel,
            f"invalid kind: {kind!r} (must be one of {sorted(IMPROVEMENT_KIND_VALUES)})",
        )

    observed_at = fm.get("observed_at")
    if observed_at not in (None, "") and not ISO_DATE_RE.match(str(observed_at)):
        result.error(
            rel,
            f"observed_at must be ISO date YYYY-MM-DD, got {observed_at!r}",
        )

    domain = fm.get("domain")
    if domain not in (None, "") and domain not in IMPROVEMENT_DOMAIN_VALUES:
        result.error(
            rel,
            f"invalid domain: {domain!r} (must be one of {sorted(IMPROVEMENT_DOMAIN_VALUES)})",
        )

    severity = fm.get("severity")
    if severity not in (None, "") and severity not in IMPROVEMENT_SEVERITY_VALUES:
        result.error(
            rel,
            f"invalid severity: {severity!r} (must be one of {sorted(IMPROVEMENT_SEVERITY_VALUES)})",
        )

    status = fm.get("status")
    if status not in (None, "") and status not in IMPROVEMENT_STATUS_VALUES:
        result.error(
            rel,
            f"invalid status: {status!r} (must be one of {sorted(IMPROVEMENT_STATUS_VALUES)})",
        )

    related = fm.get("related", [])
    if isinstance(related, list):
        for ref in related:
            if not isinstance(ref, str) or not ref:
                continue
            if "/" in ref:
                if not (wiki_dir / ref).exists():
                    result.error(rel, f"related: target not found: {ref}")
            else:
                stem = ref[:-3] if ref.endswith(".md") else ref
                if stem not in all_stems:
                    result.error(rel, f"related: target not found: {ref}")


def _validate_checklist_items(rel: str, body: str, result: LintResult) -> None:
    """All bullets under ``## Items`` must use markdown task-list syntax."""
    m = re.search(r"^##\s+Items\b.*$", body, re.MULTILINE)
    if not m:
        return
    section_start = m.end()
    next_h = re.search(r"^##\s+", body[section_start:], re.MULTILINE)
    section_end = section_start + next_h.start() if next_h else len(body)
    section = body[section_start:section_end]

    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        if not re.match(r"^- \[[ xX]\]\s", stripped):
            preview = stripped[:60]
            result.error(rel, f"checklist item not in task-list syntax: {preview!r}")


def lint(
    result: LintResult,
    wiki_dir: Path = None,
    raw_dir: Path = None,
    check_immutability: bool = False,
) -> None:
    wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR
    raw_dir = raw_dir if raw_dir is not None else RAW_DIR
    data_dir = wiki_dir.parent

    pages, paths_by_stem = collect_pages(wiki_dir)
    all_stems = set(pages.keys())

    # ── 0. Stem collisions ──────────────────────────────────────────────
    # Obsidian wikilinks are stem-keyed, so two pages sharing a stem make
    # ``[[Foo]]`` ambiguous and used to silently drop one file from
    # ``pages`` entirely. Subject hubs (``_index.md``) intentionally share
    # their stem across subjects and are exempt.
    for stem, paths in paths_by_stem.items():
        if stem in COLLISION_EXEMPT_STEMS or len(paths) <= 1:
            continue
        rel_paths = sorted(str(p.relative_to(wiki_dir)) for p in paths)
        for rel_path in rel_paths:
            others = [op for op in rel_paths if op != rel_path]
            result.error(
                rel_path,
                f"stem collision: '{stem}' also used by {', '.join(others)}",
            )

    # Build inbound link map for orphan detection
    inbound: dict[str, set[str]] = {stem: set() for stem in all_stems}

    for stem, content in pages.items():
        rel = _find_relative(stem, wiki_dir)
        links = extract_links(content)
        fm_raw = get_raw_frontmatter(content)
        fm = parse_frontmatter(content)
        body = (
            content.split("---", 2)[2]
            if content.startswith("---") and content.count("---") >= 2
            else content
        )

        # ── 1. Dead wikilinks ───────────────────────────────────────────
        for link in links:
            if link in all_stems:
                inbound[link].add(stem)
            else:
                result.error(rel, f"dead link [[{link}]]")

        # ── 2. .md in link target ───────────────────────────────────────
        for link in links:
            if ".md" in link:
                result.error(rel, f"wikilink contains .md extension: [[{link}]]")

        # ── 3. Self-links ───────────────────────────────────────────────
        for link in links:
            if link == stem:
                result.warn(rel, "links to itself")

        # ── 4. LaTeX / HTML ─────────────────────────────────────────────
        if re.search(r"\$[^$]+\$", body):
            result.error(rel, "contains LaTeX ($...$) — use plain text arrows (→)")
        if re.search(r"\\rightarrow|\\leftarrow|\\times|\\frac", body):
            result.error(rel, "contains LaTeX commands — use Obsidian markdown only")
        if re.search(r"<(?!!--)[a-zA-Z]", body):
            # Allow <!-- comments --> but flag <div>, <span>, etc.
            html_tags = re.findall(r"<([a-zA-Z]+)", body)
            non_comment = [t for t in html_tags if t not in ("br",)]
            if non_comment:
                result.warn(rel, f"contains HTML tags: {', '.join(set(non_comment))}")

        # ── 5. Unfilled placeholders ────────────────────────────────────
        # Accept both `<!-- LLM: -->` (legacy) and `<!-- LLM TODO: -->`
        # (canonical wiki template marker) so the lint stays aligned with
        # what wiki templates emit.
        placeholders = re.findall(r"<!--\s*LLM(?:\s+TODO)?:.*?-->", body)
        if placeholders:
            result.warn(
                rel, f"{len(placeholders)} unfilled <!-- LLM TODO: --> placeholder(s)"
            )

        # ── 6. Frontmatter format ───────────────────────────────────────
        if fm is None:
            result.error(rel, "missing or invalid frontmatter")
            continue

        # Quoted type values
        if re.search(r'type:\s*"', fm_raw):
            result.error(rel, 'type value is quoted ("entity") — should be unquoted')

        # Inline list style for sources
        if re.search(r"sources:\s*\[", fm_raw):
            sources_inline = fm_raw.split("sources:")[1].split("\n")[0].strip()
            if sources_inline != "[]":
                result.error(rel, "sources uses inline [...] format — use block style")

        # Missing or unknown type (must come before required-field loop —
        # an empty/unknown type silently disables the loop otherwise).
        page_type = fm.get("type", "")
        if not page_type:
            result.error(rel, "missing frontmatter field: type")
        elif page_type not in REQUIRED_FM_FIELDS:
            result.warn(rel, f"unknown type: {page_type}")

        # Missing required fields
        required = REQUIRED_FM_FIELDS.get(page_type, [])
        for field in required:
            if field not in fm:
                result.error(rel, f"missing frontmatter field: {field}")

        if page_type == "improvement":
            _validate_improvement_fm(rel, fm, result, all_stems, wiki_dir)
        elif page_type == "checklist":
            _validate_checklist_items(rel, body, result)

        # ── 7. Empty relation parens ────────────────────────────────────
        if "## Relationships" in body:
            rel_section = body.split("## Relationships")[1].split("##")[0]
            if "()" in rel_section:
                result.warn(rel, "empty () in Relationships section")

        # ── 8. Empty sections ───────────────────────────────────────────
        headings = list(re.finditer(r"^##\s+.+$", body, re.MULTILINE))
        for i, match in enumerate(headings):
            start = match.end()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
            section_content = body[start:end].strip()
            # Skip if it's just a placeholder comment
            if not section_content:
                heading_text = match.group().strip()
                result.warn(rel, f"empty section: {heading_text}")

        # ── 9. Stale sources ────────────────────────────────────────────
        sources = fm.get("sources", [])
        if isinstance(sources, list):
            for src in sources:
                if isinstance(src, str) and src:
                    src_path = data_dir / src
                    if not src_path.exists():
                        result.error(rel, f"source file not found: {src}")

        # ── 10. Stub pages ──────────────────────────────────────────────
        # Subject hubs at entities/{subject}/_index.md are excluded — they're
        # allowed to be short, check_index_sync handles them separately. Other
        # files happening to be named _index.md (outside entities/) still get
        # the stub check.
        rel_posix = rel.replace("\\", "/")
        is_subject_hub = stem == "_index" and "entities/" in rel_posix
        if not is_subject_hub:
            if len(body.strip()) < STUB_THRESHOLD_CHARS:
                result.warn(
                    rel,
                    f"stub page — body {len(body.strip())} chars (< {STUB_THRESHOLD_CHARS})",
                )

    # ── 11. Orphan pages ────────────────────────────────────────────────
    # Subject hubs (`_index.md`) are not link targets by convention
    # (files starting with `_` are excluded from the link index by
    # convention), so they cannot accumulate inbound links and must be
    # excluded from orphan detection.
    for stem in all_stems:
        if stem in ("index", "_index"):
            continue
        if not inbound.get(stem):
            result.warn(
                _find_relative(stem, wiki_dir), "orphan page — no inbound links"
            )

    # ── 12. Subject _index.md ↔ disk sync ───────────────────────────────
    check_index_sync(result, wiki_dir)

    # ── 13. Raw frontmatter required fields (always-on) ─────────────────
    check_raw_frontmatter(result, raw_dir)

    # ── 14. Raw immutability (opt-in: --check-immutability or --strict) ─
    if check_immutability:
        check_raw_captured_at_mtime(result, raw_dir)
        check_raw_immutability(result, raw_dir, data_dir)


def _find_relative(stem: str, wiki_dir: Path = None) -> str:
    """Find relative path for a page stem."""
    wiki_dir = wiki_dir if wiki_dir is not None else WIKI_DIR
    for f in wiki_dir.rglob("*.md"):
        if f.stem == stem:
            return str(f.relative_to(wiki_dir))
    return stem


def check_index_sync(result: LintResult, wiki_dir: Path = None) -> None:
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


def check_raw_frontmatter(result: LintResult, raw_dir: Path = None) -> None:
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


def check_raw_captured_at_mtime(result: LintResult, raw_dir: Path = None) -> None:
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
    result: LintResult, raw_dir: Path = None, data_dir: Path = None
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


def main():
    strict = "--strict" in sys.argv
    check_immutability = "--check-immutability" in sys.argv or strict

    print("Linting wiki/...\n")

    result = LintResult()
    lint(result, check_immutability=check_immutability)
    result.print_report()

    if not result.ok:
        print("\nFAILED — fix errors before committing.")
        sys.exit(1)
    elif strict and result.warnings:
        print("\nFAILED (--strict) — warnings treated as errors.")
        sys.exit(1)
    else:
        print("\nPASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
