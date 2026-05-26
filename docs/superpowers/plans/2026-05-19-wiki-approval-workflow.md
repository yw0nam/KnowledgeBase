# Wiki Approval Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a `review_status` field (`not_processed | pending_for_approve | approved`) on six wiki page types, with a new `kb-wiki-review` CLI managing transitions, a TTL cron auto-rejecting stale drafts, and lint/index filtering for approved-only content. Rejected pages move to `data/rejected/`. Spec: `docs/superpowers/specs/2026-05-19-wiki-approval-workflow-design.md`.

**Architecture:** Frontmatter-only state (no folder shuffling for active lifecycle). Reject is a terminal exit that moves files to `data/rejected/` as audit data. Lint/index code learns to filter by `review_status`. New CLI is a small package `src/kb/cli/wiki_review/`. Migration is a one-shot Python script documented in the spec (no permanent migrate subcommand).

**Tech Stack:** Python 3.11, PyYAML for reading frontmatter, regex-based writeback to preserve YAML format/comments, pytest for tests, uv for dependency/script management.

---

## Repository Layout Note

- **Outer repo** (`/home/spow12/codes/KnowledgeBase`): all code, templates, docs, scripts/. Tracked in git, pushed.
- **Nested data repo** (`/home/spow12/codes/KnowledgeBase/data/.git`): wiki pages, raw sources, handoffs, rejected/. Local-only, never pushed. The outer `.gitignore` excludes `data/`.

When a task says "commit in outer repo" run git from `/home/spow12/codes/KnowledgeBase`. When a task says "commit in data repo" run git from `/home/spow12/codes/KnowledgeBase/data`.

## File Structure

### New files (outer repo)

```
src/kb/cli/wiki_review/
├── __init__.py          # main() entry, argparse dispatch
├── _store.py            # frontmatter R/W, stem resolution, page enumeration
├── _feedback.py         # User Feedback section management
└── _commands.py         # one function per subcommand

scripts/cron/kb-wiki-ttl-sweep.sh   # TTL cron wrapper

test/test_wiki_review.py            # CLI integration tests

docs/workflows/wiki-approval-workflow.md   # operator manual
```

### Modified files (outer repo)

- `src/kb/cli/wiki/validators.py` — `REVIEW_STATUS_VALUES` enum + helper, `IMPROVEMENT_STATUS_VALUES → IMPROVEMENT_ISSUE_STATUS_VALUES` rename, `_validate_improvement_fm` reads `issue_status`.
- `src/kb/cli/lint_wiki.py` — `REQUIRED_FM_FIELDS` updates (review_status added to 6 types, improvement gets `issue_status` instead of `status`), orphan-check relaxation.
- `src/kb/cli/wiki/index.py` — `build_index` filters `review_status == "approved"`.
- `src/kb/cli/wiki/checks.py` — `check_index_sync` + `check_global_index_sync` filter by approved.
- `templates/wiki/{entity,concept,decision,improvement,checklist,question}.md` — add `review_status: not_processed`; improvement also `status:` → `issue_status:`.
- `test/test_lint_wiki.py` — fixture `_improvement_fm` uses `issue_status:`; add tests for `REVIEW_STATUS_VALUES` and filter behavior.
- `pyproject.toml` — add `kb-wiki-review` script entry.
- `CLAUDE.md` (outer) — review_status guidance, edit policy, subject `_index.md` hub note.

### Modified files (data nested repo, migration step)

- `data/wiki/**/*.md` (6 in-scope types) — add `review_status: pending_for_approve`.
- `data/wiki/improvements/2026-05/KB_Usage_Report_Restructure_Blockers.md` — rename `status:` → `issue_status:`.
- `data/wiki/INDEX.md` — regenerated (approved-only filter; will become empty post-migration since all are pending).

---

## Task 1: Validators — REVIEW_STATUS_VALUES + IMPROVEMENT rename

**Files:**
- Modify: `src/kb/cli/wiki/validators.py`
- Test: `test/test_lint_wiki.py` (find the `_improvement_fm` fixture around line 518; add a new test block for `REVIEW_STATUS_VALUES`)

- [ ] **Step 1: Write failing test for IMPROVEMENT_ISSUE_STATUS_VALUES rename**

Append to `test/test_lint_wiki.py`:

```python
def test_improvement_issue_status_enum_renamed(lint_mod):
    """IMPROVEMENT_STATUS_VALUES is renamed to IMPROVEMENT_ISSUE_STATUS_VALUES."""
    from kb.cli.wiki import validators

    assert hasattr(validators, "IMPROVEMENT_ISSUE_STATUS_VALUES")
    assert validators.IMPROVEMENT_ISSUE_STATUS_VALUES == frozenset(
        {"open", "acknowledged", "resolved", "wontfix"}
    )
    assert not hasattr(validators, "IMPROVEMENT_STATUS_VALUES")
```

- [ ] **Step 2: Write failing test for REVIEW_STATUS_VALUES enum**

Append to `test/test_lint_wiki.py`:

```python
def test_review_status_values_enum(lint_mod):
    from kb.cli.wiki import validators

    assert validators.REVIEW_STATUS_VALUES == frozenset(
        {"not_processed", "pending_for_approve", "approved"}
    )
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest test/test_lint_wiki.py::test_improvement_issue_status_enum_renamed test/test_lint_wiki.py::test_review_status_values_enum -v`
Expected: both FAIL (`IMPROVEMENT_STATUS_VALUES` still exists; `REVIEW_STATUS_VALUES` not defined).

- [ ] **Step 4: Update validators.py — rename and add enum**

Edit `src/kb/cli/wiki/validators.py`:

```python
"""Frontmatter/body validators for wiki linting."""

from __future__ import annotations

import re
from pathlib import Path

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
IMPROVEMENT_KIND_VALUES = frozenset({"improvement", "issue", "proposal"})
IMPROVEMENT_DOMAIN_VALUES = frozenset({"cost", "correctness", "perf", "dx", "security"})
IMPROVEMENT_SEVERITY_VALUES = frozenset({"low", "med", "high"})
IMPROVEMENT_ISSUE_STATUS_VALUES = frozenset({"open", "acknowledged", "resolved", "wontfix"})

REVIEW_STATUS_VALUES = frozenset({"not_processed", "pending_for_approve", "approved"})
# Types that participate in the approval workflow (must carry review_status).
REVIEW_STATUS_TYPES = frozenset(
    {"entity", "concept", "decision", "improvement", "checklist", "question"}
)


def _validate_review_status(rel: str, fm: dict, result) -> None:
    """Validate `review_status` enum for in-scope page types.

    Existence of the field is checked by REQUIRED_FM_FIELDS in lint_wiki;
    this only validates the value when present.
    """
    rs = fm.get("review_status")
    if rs is None:
        return
    if rs not in REVIEW_STATUS_VALUES:
        result.error(
            rel,
            f"invalid review_status: {rs!r} (must be one of {sorted(REVIEW_STATUS_VALUES)})",
        )
```

Then update `_validate_improvement_fm` (replace the `status` block, around line 51-56):

```python
    issue_status = fm.get("issue_status")
    if issue_status not in (None, "") and issue_status not in IMPROVEMENT_ISSUE_STATUS_VALUES:
        result.error(
            rel,
            f"invalid issue_status: {issue_status!r} (must be one of {sorted(IMPROVEMENT_ISSUE_STATUS_VALUES)})",
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest test/test_lint_wiki.py::test_improvement_issue_status_enum_renamed test/test_lint_wiki.py::test_review_status_values_enum -v`
Expected: both PASS.

- [ ] **Step 6: Update existing improvement fixture to use issue_status**

In `test/test_lint_wiki.py`, find the `_improvement_fm` helper (around line 518) and update:

```python
def _improvement_fm(
    kind: str = "improvement",
    observed_at: str = "2026-05-08",
    domain: str = "cost",
    severity: str = "high",
    issue_status: str = "open",
    related: list[str] | None = None,
) -> str:
    related = related if related is not None else []
    if not related:
        related_yaml = "[]"
    else:
        related_yaml = "\n" + "\n".join(f"  - {r}" for r in related)
    return (
        "---\n"
        "type: improvement\n"
        f"kind: {kind}\n"
        f'observed_at: "{observed_at}"\n'
        f"domain: {domain}\n"
        f"severity: {severity}\n"
        f"issue_status: {issue_status}\n"
        "review_status: approved\n"
        f"related: {related_yaml}\n"
        'created: "2026-05-08"\n'
        'updated: "2026-05-08"\n'
        "sources: []\n"
        "tags: []\n"
        "---\n"
    )
```

(Both `issue_status` AND `review_status: approved` are added — once REQUIRED_FM_FIELDS demands review_status in Task 2, existing fixtures must include it. `review_status: approved` keeps fixtures from triggering orphan/index relaxation.)

Then search the file for any tests that pass `status=` to `_improvement_fm` and rename to `issue_status=`.

- [ ] **Step 7: Run full test file to ensure no regressions**

Run: `uv run pytest test/test_lint_wiki.py -v`
Expected: all existing tests PASS (the two new ones added in steps 1-2 still pass; nothing else broken).

- [ ] **Step 8: Commit (outer repo)**

```bash
cd /home/spow12/codes/KnowledgeBase
git add src/kb/cli/wiki/validators.py test/test_lint_wiki.py
git commit -m "$(cat <<'EOF'
feat(lint): add REVIEW_STATUS_VALUES, rename IMPROVEMENT_STATUS_VALUES

Introduces the review_status enum (not_processed, pending_for_approve,
approved) plus REVIEW_STATUS_TYPES set for the 6 in-scope wiki page
types. Renames IMPROVEMENT_STATUS_VALUES → IMPROVEMENT_ISSUE_STATUS_VALUES
to disambiguate from the new review_status field.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Lint REQUIRED_FM_FIELDS + orphan check relaxation

**Files:**
- Modify: `src/kb/cli/lint_wiki.py` (REQUIRED_FM_FIELDS dict around line 111, orphan check around line 330)
- Test: `test/test_lint_wiki.py`

- [ ] **Step 1: Write failing test for required review_status field**

Append to `test/test_lint_wiki.py`:

```python
def test_review_status_required_for_in_scope_types(lint_mod, tmp_path):
    """Pages of in-scope types must declare review_status."""
    wiki = make_wiki_root(tmp_path)
    fm_no_review_status = """\
---
type: entity
created: "2026-04-27"
updated: "2026-04-27"
sources: []
aliases: []
tags: []
---
"""
    body = "Body content. " * 10
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\n## Pages\n\n- [[Foo]]\n",
    )
    write_page(
        wiki / "entities" / "Subj" / "2026-04" / "Foo.md",
        body=body,
        fm=fm_no_review_status,
    )
    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)
    field_errors = [
        e for e in result.errors
        if "Foo.md" in e and "review_status" in e
    ]
    assert len(field_errors) == 1, result.errors
```

- [ ] **Step 2: Write failing test for orphan relaxation on non-approved**

```python
def test_orphan_warning_skipped_for_non_approved(lint_mod, tmp_path):
    """non-approved pages do not trigger orphan warnings."""
    wiki = make_wiki_root(tmp_path)
    fm_pending = """\
---
type: entity
review_status: pending_for_approve
created: "2026-04-27"
updated: "2026-04-27"
sources: []
aliases: []
tags: []
---
"""
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\n## Pages\n\n",  # empty pages list — Foo is not listed
    )
    write_page(
        wiki / "entities" / "Subj" / "2026-04" / "Foo.md",
        body="Body content. " * 10,
        fm=fm_pending,
    )
    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)
    orphan_warns = [
        w for w in result.warnings if "Foo.md" in w and "orphan" in w
    ]
    assert orphan_warns == []
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `uv run pytest test/test_lint_wiki.py::test_review_status_required_for_in_scope_types test/test_lint_wiki.py::test_orphan_warning_skipped_for_non_approved -v`
Expected: both FAIL.

- [ ] **Step 4: Update REQUIRED_FM_FIELDS in lint_wiki.py**

Edit `src/kb/cli/lint_wiki.py` (around line 111-135), replace the `REQUIRED_FM_FIELDS` dict:

```python
REQUIRED_FM_FIELDS = {
    "entity": ["type", "review_status", "created", "updated", "sources", "tags"],
    "concept": ["type", "review_status", "created", "updated", "sources", "tags"],
    "decision": ["type", "review_status", "created", "updated", "sources", "tags"],
    # Improvement adds the lifecycle/severity/domain triplet plus
    # observation timestamp and back-references; enums are checked by
    # ``_validate_improvement_fm`` after the required-field loop.
    "improvement": [
        "type",
        "review_status",
        "kind",
        "observed_at",
        "domain",
        "severity",
        "issue_status",
        "related",
        "created",
        "updated",
        "sources",
        "tags",
    ],
    "checklist": ["type", "review_status", "created", "updated", "sources", "tags"],
    "summary": ["type", "created", "updated", "sources", "tags"],
    "question": ["type", "review_status", "created", "updated", "sources", "tags"],
    "index": ["type", "created", "updated"],
}
```

- [ ] **Step 5: Wire `_validate_review_status` into the per-page loop**

In `src/kb/cli/lint_wiki.py`, find the imports block (around line 65) and add:

```python
from kb.cli.wiki.validators import (
    IMPROVEMENT_DOMAIN_VALUES,
    IMPROVEMENT_ISSUE_STATUS_VALUES,
    IMPROVEMENT_KIND_VALUES,
    IMPROVEMENT_SEVERITY_VALUES,
    ISO_DATE_RE,
    REVIEW_STATUS_VALUES,
    REVIEW_STATUS_TYPES,
    _validate_checklist_items,
    _validate_improvement_fm,
    _validate_review_status,
)
```

(Replace the existing `from kb.cli.wiki.validators import (...)` block with the above. Adjust `IMPROVEMENT_STATUS_VALUES → IMPROVEMENT_ISSUE_STATUS_VALUES` in any prior import or `__all__` lists.)

Then in the per-page loop (around line 280, after the `if page_type == "improvement":` block), add:

```python
        if page_type in REVIEW_STATUS_TYPES:
            _validate_review_status(rel, fm, result)
```

- [ ] **Step 6: Relax orphan check for non-approved pages**

In `src/kb/cli/lint_wiki.py`, find the orphan loop (search for `# ── 10. Orphan pages` — around line 325), replace:

```python
    # ── 10. Orphan pages ────────────────────────────────────────────────
    # Subject hubs (`_index.md`) and the global INDEX.md are not link targets
    # by convention (subject hubs start with `_`; INDEX.md is the auto-TOC),
    # so they cannot accumulate inbound links and must be excluded from
    # orphan detection. Non-approved pages are also excluded because they are
    # not yet "official wiki" — they are awaiting review/promotion.
    for stem in all_stems:
        if stem in ("index", "_index", INDEX_STEM):
            continue
        page_content = pages.get(stem, "")
        page_fm = parse_frontmatter(page_content) or {}
        if page_fm.get("review_status") not in (None, "approved"):
            # not_processed or pending_for_approve — not yet a wiki citizen
            continue
        if not inbound.get(stem):
            result.warn(
                _find_relative(stem, wiki_dir), "orphan page — no inbound links"
            )
```

Note: pages of types outside `REVIEW_STATUS_TYPES` (e.g., summary) have no `review_status`; they get `None` and fall through to the current orphan check (preserving existing behavior).

- [ ] **Step 7: Update `__all__` in lint_wiki.py**

Find the `__all__` list in `src/kb/cli/lint_wiki.py` (around line 70-103) and:
- Replace `"IMPROVEMENT_STATUS_VALUES"` with `"IMPROVEMENT_ISSUE_STATUS_VALUES"`
- Add `"REVIEW_STATUS_VALUES"` and `"REVIEW_STATUS_TYPES"`
- Add `"_validate_review_status"`

- [ ] **Step 8: Run tests, verify they pass + nothing regresses**

Run: `uv run pytest test/test_lint_wiki.py -v`
Expected: ALL PASS. The two new tests pass; all existing tests still pass (fixtures already updated in Task 1).

- [ ] **Step 9: Commit (outer repo)**

```bash
cd /home/spow12/codes/KnowledgeBase
git add src/kb/cli/lint_wiki.py test/test_lint_wiki.py
git commit -m "$(cat <<'EOF'
feat(lint): require review_status on 6 wiki types, relax orphan check

REQUIRED_FM_FIELDS now mandates review_status for entity, concept,
decision, improvement, checklist, and question. Improvement type uses
issue_status (renamed from bare status). Orphan-page warning is
suppressed for non-approved pages — they are not yet wiki citizens.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Index filter — build_index includes only approved

**Files:**
- Modify: `src/kb/cli/wiki/index.py` (`_scan_pages` around line 41)
- Test: `test/test_wiki_index.py`

- [ ] **Step 1: Write failing test for approved-only filter**

Append to `test/test_wiki_index.py`:

```python
def test_build_index_excludes_non_approved(tmp_path):
    """build_index should skip pages with review_status != approved."""
    from kb.cli.wiki.index import build_index

    wiki = tmp_path / "wiki"
    (wiki / "entities" / "Subj").mkdir(parents=True)
    (wiki / "concepts").mkdir(parents=True)

    approved = """\
---
type: entity
review_status: approved
created: "2026-05-19"
updated: "2026-05-19"
sources: []
tags: []
---

# Approved
"""
    pending = """\
---
type: concept
review_status: pending_for_approve
created: "2026-05-19"
updated: "2026-05-19"
sources: []
tags: []
---

# Pending
"""
    not_processed = """\
---
type: concept
review_status: not_processed
created: "2026-05-19"
updated: "2026-05-19"
sources: []
tags: []
---

# NotProcessed
"""
    (wiki / "entities" / "Subj" / "Approved.md").write_text(approved)
    (wiki / "concepts" / "Pending.md").write_text(pending)
    (wiki / "concepts" / "NotProcessed.md").write_text(not_processed)

    content = build_index(wiki)
    assert "[[Approved]]" in content
    assert "[[Pending]]" not in content
    assert "[[NotProcessed]]" not in content


def test_build_index_includes_pages_without_review_status(tmp_path):
    """Pages of types outside REVIEW_STATUS_TYPES (e.g. summary) appear regardless."""
    from kb.cli.wiki.index import build_index

    wiki = tmp_path / "wiki"
    (wiki / "summaries" / "2026" / "05").mkdir(parents=True)
    summary = """\
---
type: summary
created: "2026-05-19"
updated: "2026-05-19"
sources: []
tags: []
---

# Daily memory
"""
    (wiki / "summaries" / "2026" / "05" / "2026-05-19-memory.md").write_text(summary)
    content = build_index(wiki)
    assert "[[2026-05-19-memory]]" in content
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest test/test_wiki_index.py::test_build_index_excludes_non_approved test/test_wiki_index.py::test_build_index_includes_pages_without_review_status -v`
Expected: first FAIL (build_index includes all pages), second PASS (already works).

- [ ] **Step 3: Update _scan_pages to filter approved**

Edit `src/kb/cli/wiki/index.py`, replace `_scan_pages`:

```python
def _scan_pages(root: Path) -> list[tuple[Path, dict | None]]:
    """Walk root for *.md, skipping per-subject _index.md hubs and
    pages whose review_status is set but not 'approved'.

    Pages without review_status (e.g. summary type, which is out of scope)
    are included unconditionally — only review_status-bearing pages can
    be filtered out by approval state.
    """
    if not root.exists():
        return []
    out: list[tuple[Path, dict | None]] = []
    for f in sorted(root.rglob("*.md")):
        if f.name == "_index.md":
            continue
        fm = parse_frontmatter(f.read_text())
        if fm is not None:
            review_status = fm.get("review_status")
            if review_status is not None and review_status != "approved":
                continue
        out.append((f, fm))
    return out
```

- [ ] **Step 4: Run tests, verify both pass**

Run: `uv run pytest test/test_wiki_index.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit (outer repo)**

```bash
cd /home/spow12/codes/KnowledgeBase
git add src/kb/cli/wiki/index.py test/test_wiki_index.py
git commit -m "$(cat <<'EOF'
feat(index): build_index filters non-approved pages

INDEX.md now only lists pages whose review_status is 'approved'. Pages
without review_status (out-of-scope types like summary) are included
unconditionally.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Sync check filter — non-approved exempt from subject hub sync

**Files:**
- Modify: `src/kb/cli/wiki/checks.py` (`check_index_sync` around line 32)
- Test: `test/test_lint_wiki.py`

- [ ] **Step 1: Write failing test for sync-warning relaxation**

Append to `test/test_lint_wiki.py`:

```python
def test_subject_index_sync_skips_non_approved(lint_mod, tmp_path):
    """A pending page on disk that's not listed in _index.md should NOT warn."""
    wiki = make_wiki_root(tmp_path)
    fm_pending = """\
---
type: entity
review_status: pending_for_approve
created: "2026-04-27"
updated: "2026-04-27"
sources: []
aliases: []
tags: []
---
"""
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\n## Pages\n\n",
    )
    write_page(
        wiki / "entities" / "Subj" / "2026-04" / "Foo.md",
        body="Body content. " * 10,
        fm=fm_pending,
    )
    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)
    listing_warns = [
        w for w in result.warnings
        if "Foo.md" in w and "not listed in" in w
    ]
    assert listing_warns == []


def test_subject_index_sync_still_warns_for_approved(lint_mod, tmp_path):
    """An approved page on disk that's not listed in _index.md SHOULD warn."""
    wiki = make_wiki_root(tmp_path)
    fm_approved = """\
---
type: entity
review_status: approved
created: "2026-04-27"
updated: "2026-04-27"
sources: []
aliases: []
tags: []
---
"""
    write_page(
        wiki / "entities" / "Subj" / "_index.md",
        "# Subj\n\n## Pages\n\n",
    )
    write_page(
        wiki / "entities" / "Subj" / "2026-04" / "Foo.md",
        body="Body content. " * 10,
        fm=fm_approved,
    )
    result = lint_mod.LintResult()
    lint_mod.lint(result, wiki_dir=wiki)
    listing_warns = [
        w for w in result.warnings
        if "Foo.md" in w and "not listed in" in w
    ]
    assert len(listing_warns) == 1
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest test/test_lint_wiki.py::test_subject_index_sync_skips_non_approved test/test_lint_wiki.py::test_subject_index_sync_still_warns_for_approved -v`
Expected: first FAIL (warning emitted), second PASS (current behavior).

- [ ] **Step 3: Update check_index_sync to filter by review_status**

Edit `src/kb/cli/wiki/checks.py`, replace the on-disk stem collection in `check_index_sync` (around line 79-81):

```python
        on_disk_stems = set()
        for f in subject_dir.rglob("*.md"):
            if f.stem == "_index":
                continue
            # Only approved (or non-review-status) pages count toward sync.
            page_fm = _parse_yaml_frontmatter(f.read_text())
            if page_fm and page_fm.get("review_status") not in (None, "approved"):
                continue
            on_disk_stems.add(f.stem)
```

Note: `_parse_yaml_frontmatter` is already imported at the top of `checks.py`.

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest test/test_lint_wiki.py::test_subject_index_sync_skips_non_approved test/test_lint_wiki.py::test_subject_index_sync_still_warns_for_approved -v`
Expected: both PASS.

- [ ] **Step 5: Run full lint test suite for regressions**

Run: `uv run pytest test/test_lint_wiki.py -v`
Expected: all PASS.

- [ ] **Step 6: Note about check_global_index_sync**

`check_global_index_sync` delegates to `build_index` (already filtered in Task 3), so no further code change is needed. The expected INDEX.md content already excludes non-approved.

- [ ] **Step 7: Commit (outer repo)**

```bash
cd /home/spow12/codes/KnowledgeBase
git add src/kb/cli/wiki/checks.py test/test_lint_wiki.py
git commit -m "$(cat <<'EOF'
feat(lint): subject _index.md sync ignores non-approved pages

check_index_sync now only flags approved pages as missing from the
subject hub. Pages with review_status of not_processed or
pending_for_approve can sit on disk without being listed — they are
not yet wiki citizens.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Update wiki templates

**Files:**
- Modify: `templates/wiki/entity.md`, `concept.md`, `decision.md`, `improvement.md`, `checklist.md`, `question.md`

- [ ] **Step 1: Update entity.md**

Replace `templates/wiki/entity.md`:

```markdown
---
type: entity
review_status: not_processed
created: ""
updated: ""
sources: []
aliases: []
tags: []
---

# {{EntityName}}

## Overview

## Key Details

## Related
```

- [ ] **Step 2: Update concept.md**

Read current content via `cat templates/wiki/concept.md` to preserve unique sections. Then add `review_status: not_processed` immediately after `type: concept`.

- [ ] **Step 3: Update decision.md**

Same pattern: `review_status: not_processed` immediately after `type: decision`.

- [ ] **Step 4: Update improvement.md**

Replace `templates/wiki/improvement.md`:

```markdown
---
type: improvement
review_status: not_processed
kind: improvement
observed_at: ""
domain: ""
severity: ""
issue_status: open
related: []
created: ""
updated: ""
sources: []
tags: []
---

# {{ImprovementTitle}}

## Observation

## Impact

## Proposed Action

## Notes
```

- [ ] **Step 5: Update checklist.md**

Same pattern: `review_status: not_processed` after `type: checklist`.

- [ ] **Step 6: Update question.md**

Same pattern: `review_status: not_processed` after `type: question`.

- [ ] **Step 7: Verify summaries unchanged**

```bash
ls templates/wiki/summaries/
cat templates/wiki/summaries/weekly.md | head -10
```

Confirm `summaries/{daily,weekly,monthly}.md` are NOT modified (summary type is out of scope).

- [ ] **Step 8: Commit (outer repo)**

```bash
cd /home/spow12/codes/KnowledgeBase
git add templates/wiki/entity.md templates/wiki/concept.md templates/wiki/decision.md templates/wiki/improvement.md templates/wiki/checklist.md templates/wiki/question.md
git commit -m "$(cat <<'EOF'
feat(templates): add review_status to 6 in-scope wiki templates

New pages default to review_status: not_processed. The improvement
template also renames bare 'status' to 'issue_status' to disambiguate
from the new review_status field. Summary templates are unchanged
(out of scope).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: CLI helper module — `_store.py`

**Files:**
- Create: `src/kb/cli/wiki_review/__init__.py` (empty package marker for now)
- Create: `src/kb/cli/wiki_review/_store.py`
- Create: `test/test_wiki_review.py`

- [ ] **Step 1: Write failing tests for stem resolution**

Create `test/test_wiki_review.py`:

```python
"""Tests for kb-wiki-review CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from kb.cli.wiki_review import _store


def _write_page(path: Path, fm: dict, body: str = "Body. " * 20) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    path.write_text("\n".join(lines))


def test_resolve_stem_unique(tmp_path):
    wiki = tmp_path / "wiki"
    _write_page(
        wiki / "entities" / "Subj" / "2026-05" / "Foo.md",
        {"type": "entity", "review_status": "not_processed",
         "created": '"2026-05-01"', "updated": '"2026-05-01"',
         "sources": "[]", "aliases": "[]", "tags": "[]"},
    )
    assert _store.resolve_stem(wiki, "Foo").name == "Foo.md"


def test_resolve_stem_collision_errors(tmp_path):
    wiki = tmp_path / "wiki"
    _write_page(
        wiki / "entities" / "A" / "Foo.md",
        {"type": "entity", "review_status": "not_processed",
         "created": '"2026-05-01"', "updated": '"2026-05-01"',
         "sources": "[]", "aliases": "[]", "tags": "[]"},
    )
    _write_page(
        wiki / "entities" / "B" / "Foo.md",
        {"type": "entity", "review_status": "not_processed",
         "created": '"2026-05-01"', "updated": '"2026-05-01"',
         "sources": "[]", "aliases": "[]", "tags": "[]"},
    )
    with pytest.raises(_store.StemCollision) as exc:
        _store.resolve_stem(wiki, "Foo")
    assert "entities/A/Foo.md" in str(exc.value)
    assert "entities/B/Foo.md" in str(exc.value)


def test_resolve_stem_not_found(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    with pytest.raises(_store.PageNotFound):
        _store.resolve_stem(wiki, "Nope")
```

- [ ] **Step 2: Write failing tests for frontmatter set_field**

Append to `test/test_wiki_review.py`:

```python
def test_set_field_updates_existing(tmp_path):
    p = tmp_path / "page.md"
    p.write_text(
        "---\n"
        "type: entity\n"
        "review_status: not_processed\n"
        "created: \"2026-05-19\"\n"
        "---\n"
        "\nBody.\n"
    )
    _store.set_frontmatter_field(p, "review_status", "approved")
    text = p.read_text()
    assert "review_status: approved\n" in text
    assert "review_status: not_processed" not in text
    assert "type: entity\n" in text  # unrelated fields preserved


def test_set_field_appends_when_missing(tmp_path):
    p = tmp_path / "page.md"
    p.write_text(
        "---\n"
        "type: entity\n"
        "created: \"2026-05-19\"\n"
        "---\n"
        "\nBody.\n"
    )
    _store.set_frontmatter_field(p, "review_status", "pending_for_approve")
    text = p.read_text()
    assert "review_status: pending_for_approve\n" in text
    # Field is appended inside frontmatter (before closing ---), order preserved.
    fm_block = text.split("---")[1]
    assert "type: entity" in fm_block
    assert "review_status: pending_for_approve" in fm_block


def test_get_field_reads_value(tmp_path):
    p = tmp_path / "page.md"
    p.write_text(
        "---\n"
        "type: entity\n"
        "review_status: approved\n"
        "created: \"2026-05-19\"\n"
        "---\n"
        "\nBody.\n"
    )
    assert _store.get_frontmatter_field(p, "review_status") == "approved"
    assert _store.get_frontmatter_field(p, "type") == "entity"
    assert _store.get_frontmatter_field(p, "missing") is None
```

- [ ] **Step 3: Run tests, verify they fail (module not found)**

Run: `uv run pytest test/test_wiki_review.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kb.cli.wiki_review'`.

- [ ] **Step 4: Create package __init__.py**

Create `src/kb/cli/wiki_review/__init__.py`:

```python
"""kb-wiki-review CLI — manage review_status lifecycle of wiki pages."""
```

- [ ] **Step 5: Create _store.py with stem resolution + frontmatter R/W**

Create `src/kb/cli/wiki_review/_store.py`:

```python
"""Frontmatter R/W and page enumeration helpers for kb-wiki-review.

Frontmatter writes use targeted regex substitution rather than
yaml.dump to preserve formatting, comments, key order, and quoting
across edits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from kb import REPO_ROOT
from kb.cli.wiki.validators import REVIEW_STATUS_TYPES

WIKI_DIR = REPO_ROOT / "data" / "wiki"
REJECTED_DIR = REPO_ROOT / "data" / "rejected"


class PageNotFound(Exception):
    """The given stem matches no page under wiki/."""


class StemCollision(Exception):
    """Multiple pages share the given stem."""


@dataclass
class Page:
    path: Path
    rel: Path  # relative to wiki_dir
    fm: dict

    @property
    def stem(self) -> str:
        return self.path.stem


def resolve_stem(wiki_dir: Path, stem: str) -> Path:
    """Find a unique <stem>.md under wiki_dir.

    Raises PageNotFound or StemCollision when ambiguous.
    """
    matches = [
        p for p in wiki_dir.rglob(f"{stem}.md")
        if p.name != "_index.md"
    ]
    if not matches:
        raise PageNotFound(f"no page with stem {stem!r} in wiki/")
    if len(matches) > 1:
        rels = sorted(str(p.relative_to(wiki_dir)) for p in matches)
        raise StemCollision(
            f"stem {stem!r} matches multiple files:\n  - "
            + "\n  - ".join(rels)
            + "\nPass an explicit relative path instead."
        )
    return matches[0]


def _split_frontmatter(text: str) -> tuple[str, str] | None:
    """Return (fm_block, body) or None if no frontmatter detected.

    fm_block does NOT include the surrounding '---' fences.
    """
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    return parts[1], parts[2]


def get_frontmatter_field(path: Path, key: str) -> str | None:
    """Return the YAML-decoded value of a top-level frontmatter field."""
    text = path.read_text()
    parts = _split_frontmatter(text)
    if parts is None:
        return None
    fm_block, _ = parts
    try:
        fm = yaml.safe_load(fm_block) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    val = fm.get(key)
    return None if val is None else str(val)


def set_frontmatter_field(path: Path, key: str, value: str) -> None:
    """Set a top-level field in frontmatter, preserving file formatting.

    If the field exists (matched as ``^key:``), its value is replaced.
    If absent, the line is appended to the frontmatter block.
    Unquoted scalar values only — use add_frontmatter_lines for complex types.
    """
    text = path.read_text()
    parts = _split_frontmatter(text)
    if parts is None:
        raise ValueError(f"{path}: missing or malformed frontmatter")
    fm_block, body = parts

    pattern = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
    if pattern.search(fm_block):
        new_fm = pattern.sub(f"{key}: {value}", fm_block, count=1)
    else:
        new_fm = fm_block.rstrip("\n") + f"\n{key}: {value}\n"

    path.write_text(f"---{new_fm}---{body}")


def add_frontmatter_lines(path: Path, lines: list[str]) -> None:
    """Append raw YAML lines to the frontmatter block (e.g. with quoted values).

    Each line must already include the ``key: value`` form; no escaping is done.
    Used for adding fields like ``rejected_at: "2026-05-19T..."`` and lists.
    """
    text = path.read_text()
    parts = _split_frontmatter(text)
    if parts is None:
        raise ValueError(f"{path}: missing or malformed frontmatter")
    fm_block, body = parts
    appended = "\n".join(lines)
    new_fm = fm_block.rstrip("\n") + "\n" + appended + "\n"
    path.write_text(f"---{new_fm}---{body}")


def iter_pages(wiki_dir: Path) -> list[Page]:
    """Yield every in-scope page (REVIEW_STATUS_TYPES) under wiki_dir."""
    out: list[Page] = []
    for f in sorted(wiki_dir.rglob("*.md")):
        if f.name == "_index.md" or f.name == "INDEX.md":
            continue
        text = f.read_text()
        parts = _split_frontmatter(text)
        if parts is None:
            continue
        try:
            fm = yaml.safe_load(parts[0]) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict):
            continue
        if fm.get("type") not in REVIEW_STATUS_TYPES:
            continue
        out.append(Page(path=f, rel=f.relative_to(wiki_dir), fm=fm))
    return out
```

- [ ] **Step 6: Run tests, verify they pass**

Run: `uv run pytest test/test_wiki_review.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 7: Commit (outer repo)**

```bash
cd /home/spow12/codes/KnowledgeBase
git add src/kb/cli/wiki_review/ test/test_wiki_review.py
git commit -m "$(cat <<'EOF'
feat(wiki-review): add _store helpers for kb-wiki-review

Stem resolution with collision detection, regex-based frontmatter
read/write that preserves formatting and quoting, and page
enumeration filtered to the 6 in-scope wiki types.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: User Feedback body section helper — `_feedback.py`

**Files:**
- Create: `src/kb/cli/wiki_review/_feedback.py`
- Test: `test/test_wiki_review.py`

- [ ] **Step 1: Write failing tests for feedback append**

Append to `test/test_wiki_review.py`:

```python
def test_append_feedback_creates_section(tmp_path):
    from kb.cli.wiki_review import _feedback

    p = tmp_path / "page.md"
    p.write_text(
        "---\ntype: entity\n---\n\n# Title\n\nSome body.\n"
    )
    _feedback.append_feedback_line(p, "2026-05-19", "Approved", "Looks good.")
    text = p.read_text()
    assert "## User Feedback" in text
    assert "2026-05-19-Approved: Looks good." in text
    # Section appears at end of body.
    body = text.split("---", 2)[2]
    assert body.rstrip().endswith("2026-05-19-Approved: Looks good.")


def test_append_feedback_appends_to_existing_section(tmp_path):
    from kb.cli.wiki_review import _feedback

    p = tmp_path / "page.md"
    p.write_text(
        "---\ntype: entity\n---\n\n# Title\n\nBody.\n\n"
        "## User Feedback\n\n2026-05-18-Rejected: Bad sources.\n"
    )
    _feedback.append_feedback_line(p, "2026-05-19", "Approved", "Fixed.")
    text = p.read_text()
    # Both lines present, in order, under a single header.
    assert text.count("## User Feedback") == 1
    assert "2026-05-18-Rejected: Bad sources." in text
    assert "2026-05-19-Approved: Fixed." in text
    # Order: existing first, then appended.
    assert text.index("2026-05-18") < text.index("2026-05-19")


def test_append_feedback_skip_empty_input(tmp_path):
    from kb.cli.wiki_review import _feedback

    p = tmp_path / "page.md"
    original = "---\ntype: entity\n---\n\n# Title\n\nBody.\n"
    p.write_text(original)
    _feedback.append_feedback_line(p, "2026-05-19", "Approved", "")
    # File unchanged when feedback is empty.
    assert p.read_text() == original


def test_append_feedback_strips_input_whitespace(tmp_path):
    from kb.cli.wiki_review import _feedback

    p = tmp_path / "page.md"
    p.write_text("---\ntype: entity\n---\n\n# Title\n")
    _feedback.append_feedback_line(p, "2026-05-19", "Rejected", "   \n  trim me  \n")
    text = p.read_text()
    assert "2026-05-19-Rejected: trim me" in text
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest test/test_wiki_review.py -v`
Expected: 4 new tests FAIL (`_feedback` module missing).

- [ ] **Step 3: Create _feedback.py**

Create `src/kb/cli/wiki_review/_feedback.py`:

```python
"""Append User Feedback lines to wiki page bodies.

Body convention (see spec §6.3):

    ## User Feedback

    2026-05-19-Rejected: <text>
    2026-05-20-Approved: <text>
    2026-05-21-Auto-rejected: <system reason>

A single section accumulates lines from multiple review actions.
Empty input means "skip" — no line is appended (avoids noise).
"""

from __future__ import annotations

from pathlib import Path

HEADER = "## User Feedback"


def append_feedback_line(
    path: Path, date_str: str, label: str, raw_input: str
) -> None:
    """Append a feedback line of the form ``YYYY-MM-DD-Label: <text>``.

    If raw_input is empty/whitespace, the file is not modified.
    If the ## User Feedback section already exists, the line is appended
    inside it. Otherwise the section is created at end of body.
    """
    feedback = raw_input.strip()
    if not feedback:
        return

    line = f"{date_str}-{label}: {feedback}"
    text = path.read_text()

    if HEADER in text:
        # Append within the existing section, before any trailing blank lines.
        # Locate the User Feedback heading and the next ## heading (or EOF).
        header_idx = text.index(HEADER)
        # End-of-section: next top-level `## ` after the header, or EOF.
        rest_start = header_idx + len(HEADER)
        next_h = _find_next_h2(text, rest_start)
        section_end = next_h if next_h is not None else len(text)

        existing = text[header_idx:section_end].rstrip()
        new_section = existing + f"\n{line}\n"
        path.write_text(text[:header_idx] + new_section + text[section_end:])
        return

    # No existing section — append at end of body.
    body_trimmed = text.rstrip()
    new_text = body_trimmed + f"\n\n{HEADER}\n\n{line}\n"
    path.write_text(new_text)


def _find_next_h2(text: str, start: int) -> int | None:
    """Return the index of the next ``\\n## `` (level-2 heading) after start, or None."""
    needle = "\n## "
    idx = text.find(needle, start)
    return idx if idx >= 0 else None
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest test/test_wiki_review.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit (outer repo)**

```bash
cd /home/spow12/codes/KnowledgeBase
git add src/kb/cli/wiki_review/_feedback.py test/test_wiki_review.py
git commit -m "$(cat <<'EOF'
feat(wiki-review): User Feedback body section helper

Appends YYYY-MM-DD-<Label>: <text> lines to a single ## User Feedback
section. Creates the section on first use, appends to existing on
subsequent calls. Empty input is a no-op (avoids noise).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: CLI commands — `_commands.py` with `promote` first

**Files:**
- Create: `src/kb/cli/wiki_review/_commands.py`
- Test: `test/test_wiki_review.py`

- [ ] **Step 1: Write failing tests for promote**

Append to `test/test_wiki_review.py`:

```python
def _make_page(wiki: Path, type_: str, stem: str, status: str = "not_processed",
                created: str = "2026-05-19", subj: str = "subj") -> Path:
    """Helper to write a syntactically valid wiki page."""
    if type_ == "entity":
        path = wiki / "entities" / subj / "2026-05" / f"{stem}.md"
    else:
        path = wiki / f"{type_}s" / f"{stem}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = ""
    if type_ == "entity":
        extra = "aliases: []\n"
    if type_ == "improvement":
        extra = (
            "kind: improvement\n"
            "observed_at: \"2026-05-19\"\n"
            "domain: dx\n"
            "severity: low\n"
            "issue_status: open\n"
            "related: []\n"
        )
    fm = (
        "---\n"
        f"type: {type_}\n"
        f"review_status: {status}\n"
        f"{extra}"
        f"created: \"{created}\"\n"
        f"updated: \"{created}\"\n"
        "sources: []\n"
        "tags: []\n"
        "---\n"
        "\n"
        f"# {stem}\n\nBody. " * 5
    )
    path.write_text(fm)
    return path


def test_promote_transitions_to_pending(tmp_path):
    from kb.cli.wiki_review import _commands, _store

    wiki = tmp_path / "wiki"
    page = _make_page(wiki, "entity", "Foo", status="not_processed")
    rc = _commands.cmd_promote(wiki, "Foo")
    assert rc == 0
    assert _store.get_frontmatter_field(page, "review_status") == "pending_for_approve"
    # No User Feedback section added (system action).
    assert "## User Feedback" not in page.read_text()


def test_promote_errors_when_already_pending(tmp_path, capsys):
    from kb.cli.wiki_review import _commands

    wiki = tmp_path / "wiki"
    _make_page(wiki, "entity", "Foo", status="pending_for_approve")
    rc = _commands.cmd_promote(wiki, "Foo")
    assert rc == 1
    captured = capsys.readouterr()
    assert "promote only from not_processed" in captured.err


def test_promote_errors_when_already_approved(tmp_path, capsys):
    from kb.cli.wiki_review import _commands

    wiki = tmp_path / "wiki"
    _make_page(wiki, "entity", "Foo", status="approved")
    rc = _commands.cmd_promote(wiki, "Foo")
    assert rc == 1
    assert "promote only from not_processed" in capsys.readouterr().err


def test_promote_errors_when_page_not_found(tmp_path, capsys):
    from kb.cli.wiki_review import _commands

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    rc = _commands.cmd_promote(wiki, "Nope")
    assert rc == 1
    assert "page not found in wiki/" in capsys.readouterr().err
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest test/test_wiki_review.py -v`
Expected: 4 new FAIL (`_commands` missing).

- [ ] **Step 3: Create _commands.py with promote**

Create `src/kb/cli/wiki_review/_commands.py`:

```python
"""Subcommand implementations for kb-wiki-review.

Each cmd_* function takes a wiki_dir Path plus stem/args and returns
an int exit code. Errors are printed to stderr via _err().
"""

from __future__ import annotations

import sys
from pathlib import Path

from kb.cli.wiki_review import _store


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _resolve_or_print(wiki_dir: Path, stem: str) -> Path | None:
    """Resolve stem to file path; print error and return None on failure."""
    try:
        return _store.resolve_stem(wiki_dir, stem)
    except _store.PageNotFound:
        _err(f"page not found in wiki/: {stem}")
        return None
    except _store.StemCollision as exc:
        _err(str(exc))
        return None


def cmd_promote(wiki_dir: Path, stem: str) -> int:
    """not_processed → pending_for_approve."""
    path = _resolve_or_print(wiki_dir, stem)
    if path is None:
        return 1
    current = _store.get_frontmatter_field(path, "review_status")
    if current != "not_processed":
        _err(f"promote only from not_processed (current: {current!r})")
        return 1
    _store.set_frontmatter_field(path, "review_status", "pending_for_approve")
    print(f"✓ Promoted: {path.relative_to(wiki_dir)}")
    return 0
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest test/test_wiki_review.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit (outer repo)**

```bash
cd /home/spow12/codes/KnowledgeBase
git add src/kb/cli/wiki_review/_commands.py test/test_wiki_review.py
git commit -m "feat(wiki-review): promote subcommand

Transitions not_processed → pending_for_approve. Rejects calls from
any other current status and emits 'page not found' for unknown stems.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: `approve` subcommand

**Files:**
- Modify: `src/kb/cli/wiki_review/_commands.py`
- Test: `test/test_wiki_review.py`

- [ ] **Step 1: Write failing tests for approve**

Append to `test/test_wiki_review.py`:

```python
def test_approve_with_feedback_arg(tmp_path):
    from kb.cli.wiki_review import _commands, _store

    wiki = tmp_path / "wiki"
    page = _make_page(wiki, "entity", "Foo", status="pending_for_approve")
    rc = _commands.cmd_approve(wiki, "Foo", feedback="Looks solid.", today="2026-05-19")
    assert rc == 0
    assert _store.get_frontmatter_field(page, "review_status") == "approved"
    text = page.read_text()
    assert "## User Feedback" in text
    assert "2026-05-19-Approved: Looks solid." in text


def test_approve_empty_feedback_skips_section(tmp_path):
    from kb.cli.wiki_review import _commands, _store

    wiki = tmp_path / "wiki"
    page = _make_page(wiki, "entity", "Foo", status="pending_for_approve")
    rc = _commands.cmd_approve(wiki, "Foo", feedback="", today="2026-05-19")
    assert rc == 0
    assert _store.get_frontmatter_field(page, "review_status") == "approved"
    assert "## User Feedback" not in page.read_text()


def test_approve_errors_on_not_processed(tmp_path, capsys):
    from kb.cli.wiki_review import _commands

    wiki = tmp_path / "wiki"
    _make_page(wiki, "entity", "Foo", status="not_processed")
    rc = _commands.cmd_approve(wiki, "Foo", feedback="x", today="2026-05-19")
    assert rc == 1
    assert "must be pending_for_approve" in capsys.readouterr().err


def test_approve_errors_on_already_approved(tmp_path, capsys):
    from kb.cli.wiki_review import _commands

    wiki = tmp_path / "wiki"
    _make_page(wiki, "entity", "Foo", status="approved")
    rc = _commands.cmd_approve(wiki, "Foo", feedback="x", today="2026-05-19")
    assert rc == 1
    assert "already approved" in capsys.readouterr().err
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest test/test_wiki_review.py -v`
Expected: 4 new FAIL.

- [ ] **Step 3: Add cmd_approve to _commands.py**

First, add the `_feedback` import alongside the existing imports at the top of `src/kb/cli/wiki_review/_commands.py`. The import block should now read:

```python
from __future__ import annotations

import sys
from pathlib import Path

from kb.cli.wiki_review import _feedback, _store
```

Then append the function at the end of the file:

```python
def cmd_approve(wiki_dir: Path, stem: str, feedback: str, today: str) -> int:
    """pending_for_approve → approved."""
    path = _resolve_or_print(wiki_dir, stem)
    if path is None:
        return 1
    current = _store.get_frontmatter_field(path, "review_status")
    if current == "approved":
        _err(f"already approved: {stem}")
        return 1
    if current != "pending_for_approve":
        _err(
            f"must be pending_for_approve (current: {current!r}); "
            "run promote first"
        )
        return 1
    _store.set_frontmatter_field(path, "review_status", "approved")
    _feedback.append_feedback_line(path, today, "Approved", feedback)
    print(f"✓ Approved: {path.relative_to(wiki_dir)}")
    return 0
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest test/test_wiki_review.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit (outer repo)**

```bash
cd /home/spow12/codes/KnowledgeBase
git add src/kb/cli/wiki_review/_commands.py test/test_wiki_review.py
git commit -m "feat(wiki-review): approve subcommand

Transitions pending_for_approve → approved. Appends a User Feedback
line when feedback text is non-empty. Errors on other current statuses
with explicit messages.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: `reject` subcommand (with `git mv` to `data/rejected/`)

**Files:**
- Modify: `src/kb/cli/wiki_review/_commands.py`, `_store.py` (add a rejection helper)
- Test: `test/test_wiki_review.py`

- [ ] **Step 1: Write failing tests for reject**

Append to `test/test_wiki_review.py`:

```python
import subprocess


def _init_data_repo(data_dir: Path) -> None:
    """Init a real git repo at data_dir for git mv tests."""
    data_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=data_dir, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "--allow-empty", "-q", "-m", "init"],
        cwd=data_dir, check=True,
    )


def test_reject_moves_file_to_rejected_tree(tmp_path):
    from kb.cli.wiki_review import _commands, _store

    data = tmp_path / "data"
    _init_data_repo(data)
    wiki = data / "wiki"
    rejected = data / "rejected"
    page = _make_page(wiki, "entity", "Foo", status="pending_for_approve")
    subprocess.run(["git", "add", "."], cwd=data, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "-m", "add Foo"],
        cwd=data, check=True,
    )

    rc = _commands.cmd_reject(
        wiki_dir=wiki, rejected_dir=rejected, data_dir=data,
        stem="Foo", feedback="Bad sources.", today="2026-05-19",
        now_iso="2026-05-19T14:30:00+09:00", rejected_by="user",
    )
    assert rc == 0
    assert not page.exists()
    moved = rejected / "entities" / "subj" / "2026-05" / "Foo.md"
    assert moved.exists()
    text = moved.read_text()
    assert "review_status: rejected" in text
    assert 'rejected_at: "2026-05-19T14:30:00+09:00"' in text
    assert "rejected_by: user" in text
    assert "2026-05-19-Rejected: Bad sources." in text


def test_reject_errors_on_not_pending(tmp_path, capsys):
    from kb.cli.wiki_review import _commands

    data = tmp_path / "data"
    _init_data_repo(data)
    wiki = data / "wiki"
    _make_page(wiki, "entity", "Foo", status="not_processed")
    rc = _commands.cmd_reject(
        wiki_dir=wiki, rejected_dir=data / "rejected", data_dir=data,
        stem="Foo", feedback="x", today="2026-05-19",
        now_iso="2026-05-19T14:30:00+09:00", rejected_by="user",
    )
    assert rc == 1
    assert "must be pending_for_approve" in capsys.readouterr().err


def test_reject_collision_errors(tmp_path, capsys):
    from kb.cli.wiki_review import _commands

    data = tmp_path / "data"
    _init_data_repo(data)
    wiki = data / "wiki"
    rejected = data / "rejected"
    page = _make_page(wiki, "entity", "Foo", status="pending_for_approve")
    # Pre-existing collision at the rejected destination.
    dest = rejected / "entities" / "subj" / "2026-05" / "Foo.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("already here")

    rc = _commands.cmd_reject(
        wiki_dir=wiki, rejected_dir=rejected, data_dir=data,
        stem="Foo", feedback="x", today="2026-05-19",
        now_iso="2026-05-19T14:30:00+09:00", rejected_by="user",
    )
    assert rc == 1
    assert "already exists" in capsys.readouterr().err
    # Original wiki file untouched on collision.
    assert page.exists()
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest test/test_wiki_review.py -v`
Expected: 3 new FAIL.

- [ ] **Step 3: Add cmd_reject to _commands.py**

First, add `import subprocess` to the top-of-file imports in `src/kb/cli/wiki_review/_commands.py`:

```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from kb.cli.wiki_review import _feedback, _store
```

Then append the function at the end of the file:

```python
def cmd_reject(
    wiki_dir: Path,
    rejected_dir: Path,
    data_dir: Path,
    stem: str,
    feedback: str,
    today: str,
    now_iso: str,
    rejected_by: str,
) -> int:
    """pending_for_approve → rejected (file moved out of wiki/ via git mv).

    ``rejected_by`` is ``"user"`` for interactive reject and ``"auto_ttl"`` for
    ttl-sweep auto-rejection. ``feedback`` is the User Feedback line text
    (empty for system actions skips the body append).
    ``today`` is KST-local YYYY-MM-DD; ``now_iso`` is ISO timestamp with
    timezone offset.
    """
    path = _resolve_or_print(wiki_dir, stem)
    if path is None:
        return 1
    current = _store.get_frontmatter_field(path, "review_status")
    if current == "rejected":
        _err(f"already rejected: {stem}")
        return 1
    if current != "pending_for_approve" and rejected_by == "user":
        _err(
            f"must be pending_for_approve (current: {current!r}); "
            "user reject not allowed from this state"
        )
        return 1
    if current != "not_processed" and rejected_by == "auto_ttl":
        # auto_ttl should only reach files in not_processed state — caller bug.
        _err(f"ttl-sweep target must be not_processed (current: {current!r})")
        return 1

    rel = path.relative_to(wiki_dir)
    dest = rejected_dir / rel
    if dest.exists():
        _err(
            f"rejection target already exists at "
            f"{dest.relative_to(data_dir)}; resolve manually"
        )
        return 1

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: update frontmatter + body BEFORE the move so git tracks the
    # rename + modification as a single change.
    _store.set_frontmatter_field(path, "review_status", "rejected")
    _store.add_frontmatter_lines(
        path,
        [f'rejected_at: "{now_iso}"', f"rejected_by: {rejected_by}"],
    )
    label = "Auto-rejected" if rejected_by == "auto_ttl" else "Rejected"
    _feedback.append_feedback_line(path, today, label, feedback)

    # Step 2: git mv. cwd = data_dir so paths are relative to repo root.
    src_rel = path.relative_to(data_dir)
    dest_rel = dest.relative_to(data_dir)
    try:
        subprocess.run(
            ["git", "mv", str(src_rel), str(dest_rel)],
            cwd=data_dir,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        _err(f"git mv failed: {exc.stderr.strip()}")
        return 1

    print(f"✓ Rejected: {rel} → {dest.relative_to(data_dir)}")
    return 0
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest test/test_wiki_review.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit (outer repo)**

```bash
cd /home/spow12/codes/KnowledgeBase
git add src/kb/cli/wiki_review/_commands.py test/test_wiki_review.py
git commit -m "feat(wiki-review): reject subcommand with git mv to data/rejected/

Updates frontmatter (review_status: rejected, rejected_at, rejected_by)
and appends User Feedback line, then git mv's the file to
data/rejected/<orig path>. Errors atomically when destination collides
or current status is wrong.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: `list` and `ttl-sweep` subcommands

**Files:**
- Modify: `src/kb/cli/wiki_review/_commands.py`
- Test: `test/test_wiki_review.py`

- [ ] **Step 1: Write failing tests for list**

Append to `test/test_wiki_review.py`:

```python
def test_list_filters_by_status(tmp_path, capsys):
    from kb.cli.wiki_review import _commands

    wiki = tmp_path / "wiki"
    _make_page(wiki, "entity", "A", status="not_processed", created="2026-05-15")
    _make_page(wiki, "entity", "B", status="pending_for_approve", created="2026-05-16")
    _make_page(wiki, "concept", "C", status="approved", created="2026-05-17")

    rc = _commands.cmd_list(wiki, status="pending_for_approve", counts=False, today="2026-05-19")
    assert rc == 0
    out = capsys.readouterr().out
    assert "B" in out
    assert "A" not in out
    assert "C" not in out


def test_list_all_status(tmp_path, capsys):
    from kb.cli.wiki_review import _commands

    wiki = tmp_path / "wiki"
    _make_page(wiki, "entity", "A", status="not_processed")
    _make_page(wiki, "entity", "B", status="pending_for_approve")
    _make_page(wiki, "concept", "C", status="approved")

    rc = _commands.cmd_list(wiki, status="all", counts=False, today="2026-05-19")
    assert rc == 0
    out = capsys.readouterr().out
    assert all(s in out for s in ("A", "B", "C"))


def test_list_counts(tmp_path, capsys):
    from kb.cli.wiki_review import _commands

    wiki = tmp_path / "wiki"
    _make_page(wiki, "entity", "A", status="not_processed")
    _make_page(wiki, "entity", "B", status="not_processed")
    _make_page(wiki, "entity", "C", status="pending_for_approve")
    _make_page(wiki, "concept", "D", status="approved")

    rc = _commands.cmd_list(wiki, status="all", counts=True, today="2026-05-19")
    assert rc == 0
    out = capsys.readouterr().out
    assert "2 not_processed" in out
    assert "1 pending_for_approve" in out
    assert "1 approved" in out
```

- [ ] **Step 2: Write failing test for ttl-sweep**

Append to `test/test_wiki_review.py`:

```python
def test_ttl_sweep_rejects_old_not_processed(tmp_path, capsys):
    from kb.cli.wiki_review import _commands

    data = tmp_path / "data"
    _init_data_repo(data)
    wiki = data / "wiki"
    rejected = data / "rejected"
    # 8 days old → should be swept.
    old = _make_page(wiki, "entity", "Stale", status="not_processed", created="2026-05-11")
    # 6 days old → not swept.
    young = _make_page(wiki, "entity", "Fresh", status="not_processed", created="2026-05-13")
    # pending — not swept regardless of age.
    pending = _make_page(wiki, "concept", "Pending", status="pending_for_approve", created="2026-05-01")
    subprocess.run(["git", "add", "."], cwd=data, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "-m", "seed"],
        cwd=data, check=True,
    )

    rc = _commands.cmd_ttl_sweep(
        wiki_dir=wiki, rejected_dir=rejected, data_dir=data,
        days=7, today="2026-05-19",
        now_iso="2026-05-19T00:30:00+09:00",
    )
    assert rc == 0
    assert not old.exists()
    moved = rejected / "entities" / "subj" / "2026-05" / "Stale.md"
    assert moved.exists()
    assert "auto_ttl" in moved.read_text()
    assert "Auto-rejected" in moved.read_text()
    assert young.exists()
    assert pending.exists()
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `uv run pytest test/test_wiki_review.py -v`
Expected: 4 new FAIL.

- [ ] **Step 4: Add cmd_list and cmd_ttl_sweep**

First, add `datetime` and `Counter` to the top-of-file imports in `src/kb/cli/wiki_review/_commands.py`:

```python
from __future__ import annotations

import datetime
import subprocess
import sys
from collections import Counter
from pathlib import Path

from kb.cli.wiki_review import _feedback, _store
```

Then append the function at the end of the file:

```python
def _age_days(created: str | None, today: str) -> int | None:
    if not created:
        return None
    try:
        c = datetime.date.fromisoformat(str(created).strip().strip('"'))
        t = datetime.date.fromisoformat(today)
    except ValueError:
        return None
    return (t - c).days


def cmd_list(wiki_dir: Path, status: str, counts: bool, today: str) -> int:
    """Print pages filtered by review_status (or 'all'). With --counts,
    print a one-line summary instead.
    """
    pages = _store.iter_pages(wiki_dir)

    if counts:
        bucket = Counter(p.fm.get("review_status", "?") for p in pages)
        parts = [
            f"{bucket.get(s, 0)} {s}"
            for s in ("not_processed", "pending_for_approve", "approved")
        ]
        print(", ".join(parts))
        return 0

    if status != "all":
        pages = [p for p in pages if p.fm.get("review_status") == status]

    if not pages:
        print(f"(no pages with status={status})")
        return 0

    # Format: STATUS  AGE  STEM  PATH
    rows = []
    for p in pages:
        st = str(p.fm.get("review_status") or "?")
        age = _age_days(p.fm.get("created"), today)
        age_str = f"{age}d" if age is not None else "?"
        rows.append((st, age_str, p.stem, str(p.rel)))
    width_status = max(len(r[0]) for r in rows)
    width_stem = max(len(r[2]) for r in rows)
    for st, age, stem, rel in sorted(rows, key=lambda r: (r[0], -int(r[1].rstrip("d") or 0))):
        print(f"{st.ljust(width_status)}  {age.rjust(4)}  {stem.ljust(width_stem)}  {rel}")
    return 0


def cmd_ttl_sweep(
    wiki_dir: Path,
    rejected_dir: Path,
    data_dir: Path,
    days: int,
    today: str,
    now_iso: str,
) -> int:
    """Auto-reject not_processed pages whose `created` is older than `days`."""
    swept = 0
    skipped = 0
    for page in _store.iter_pages(wiki_dir):
        if page.fm.get("review_status") != "not_processed":
            continue
        age = _age_days(page.fm.get("created"), today)
        if age is None or age < days:
            continue
        rc = cmd_reject(
            wiki_dir=wiki_dir,
            rejected_dir=rejected_dir,
            data_dir=data_dir,
            stem=page.stem,
            feedback=f"No promotion within {days}d window.",
            today=today,
            now_iso=now_iso,
            rejected_by="auto_ttl",
        )
        if rc == 0:
            swept += 1
        else:
            skipped += 1
    print(f"ttl-sweep: {swept} rejected, {skipped} skipped (errors)")
    return 0
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `uv run pytest test/test_wiki_review.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit (outer repo)**

```bash
cd /home/spow12/codes/KnowledgeBase
git add src/kb/cli/wiki_review/_commands.py test/test_wiki_review.py
git commit -m "feat(wiki-review): list and ttl-sweep subcommands

list filters pages by review_status (default pending_for_approve) and
supports --counts for a one-line summary. ttl-sweep auto-rejects
not_processed pages whose created date is older than the TTL window,
delegating to cmd_reject with rejected_by=auto_ttl.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: CLI entry point — argparse dispatch

**Files:**
- Modify: `src/kb/cli/wiki_review/__init__.py`
- Modify: `pyproject.toml` (add scripts entry)
- Test: `test/test_wiki_review.py`

- [ ] **Step 1: Write failing test for main() dispatch**

Append to `test/test_wiki_review.py`:

```python
def test_main_dispatch_list(tmp_path, capsys, monkeypatch):
    from kb.cli import wiki_review

    wiki = tmp_path / "wiki"
    _make_page(wiki, "entity", "A", status="pending_for_approve")

    # Force REPO_ROOT to our tmp tree.
    monkeypatch.setattr(
        "kb.cli.wiki_review._store.WIKI_DIR", wiki
    )
    monkeypatch.setattr(
        "kb.cli.wiki_review._store.REJECTED_DIR", tmp_path / "rejected"
    )

    rc = wiki_review.main(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "A" in out


def test_main_unknown_command(capsys):
    from kb.cli import wiki_review

    rc = wiki_review.main(["bogus"])
    assert rc != 0
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest test/test_wiki_review.py -v`
Expected: 2 new FAIL (`main` missing).

- [ ] **Step 3: Write the main() dispatcher**

Replace `src/kb/cli/wiki_review/__init__.py`:

```python
"""kb-wiki-review CLI — manage review_status lifecycle of wiki pages."""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from kb.cli.wiki_review import _commands, _store

KST = ZoneInfo("Asia/Seoul")


def _today_kst() -> str:
    return datetime.datetime.now(KST).date().isoformat()


def _now_iso_kst() -> str:
    return datetime.datetime.now(KST).isoformat(timespec="seconds")


def _read_feedback_interactive() -> str:
    """Read multi-line feedback from stdin until EOF; return stripped text."""
    print("Feedback (empty to skip, Ctrl-D when done):")
    return sys.stdin.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kb-wiki-review",
        description="Manage wiki page approval lifecycle.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List pages by review_status")
    p_list.add_argument(
        "--status",
        default="pending_for_approve",
        choices=["not_processed", "pending_for_approve", "approved", "all"],
    )
    p_list.add_argument("--counts", action="store_true",
                        help="Print one-line summary instead of listing")

    p_promote = sub.add_parser("promote",
                               help="not_processed → pending_for_approve")
    p_promote.add_argument("stem")

    p_approve = sub.add_parser("approve",
                               help="pending_for_approve → approved")
    p_approve.add_argument("stem")
    p_approve.add_argument("--feedback", default=None,
                           help="Feedback text (omit for interactive prompt)")

    p_reject = sub.add_parser("reject",
                              help="pending_for_approve → rejected (moves file)")
    p_reject.add_argument("stem")
    p_reject.add_argument("--feedback", default=None,
                          help="Feedback text (omit for interactive prompt)")

    p_ttl = sub.add_parser("ttl-sweep",
                           help="Auto-reject stale not_processed pages")
    p_ttl.add_argument("--days", type=int, default=7,
                       help="TTL in days from `created` (default 7)")

    args = parser.parse_args(argv)
    today = _today_kst()
    now = _now_iso_kst()

    if args.cmd == "list":
        return _commands.cmd_list(
            wiki_dir=_store.WIKI_DIR,
            status=args.status,
            counts=args.counts,
            today=today,
        )

    if args.cmd == "promote":
        return _commands.cmd_promote(_store.WIKI_DIR, args.stem)

    if args.cmd == "approve":
        feedback = args.feedback if args.feedback is not None else _read_feedback_interactive()
        return _commands.cmd_approve(
            wiki_dir=_store.WIKI_DIR,
            stem=args.stem,
            feedback=feedback,
            today=today,
        )

    if args.cmd == "reject":
        feedback = args.feedback if args.feedback is not None else _read_feedback_interactive()
        return _commands.cmd_reject(
            wiki_dir=_store.WIKI_DIR,
            rejected_dir=_store.REJECTED_DIR,
            data_dir=_store.WIKI_DIR.parent,
            stem=args.stem,
            feedback=feedback,
            today=today,
            now_iso=now,
            rejected_by="user",
        )

    if args.cmd == "ttl-sweep":
        return _commands.cmd_ttl_sweep(
            wiki_dir=_store.WIKI_DIR,
            rejected_dir=_store.REJECTED_DIR,
            data_dir=_store.WIKI_DIR.parent,
            days=args.days,
            today=today,
            now_iso=now,
        )

    # argparse with required=True should make this unreachable; keep for safety.
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add pyproject.toml script entry**

Edit `pyproject.toml` `[project.scripts]` block (around line 36) — add the new entry alphabetically near existing wiki ones:

```toml
[project.scripts]
kb-lint-wiki = "kb.cli.lint_wiki:main"
kb-lint-handoff = "kb.cli.lint_handoff:main"
kb-wiki-index = "kb.cli.wiki_index:main"
kb-wiki-review = "kb.cli.wiki_review:main"
kb-tool-trace-parse = "kb.cli.tool_trace_parse:main"
kb-opencode-daily-report = "kb.cli.opencode_daily_report:main"
kb-hermes-daily-report = "kb.cli.hermes_daily_report:main"
kb-claude-code-daily-report = "kb.cli.claude_code_daily_report:main"
```

- [ ] **Step 5: Sync uv**

Run: `uv sync`
Expected: exit 0, kb-wiki-review installed.

- [ ] **Step 6: Run tests, verify they pass**

Run: `uv run pytest test/test_wiki_review.py -v`
Expected: all PASS.

- [ ] **Step 7: Smoke test installed CLI**

Run: `uv run kb-wiki-review --help`
Expected: prints help text with 5 subcommands.

Run: `uv run kb-wiki-review list --counts`
Expected: may fail before migration (existing pages lack review_status) or succeed with a summary line. Either is OK at this stage — the next task handles migration.

- [ ] **Step 8: Commit (outer repo)**

```bash
cd /home/spow12/codes/KnowledgeBase
git add src/kb/cli/wiki_review/__init__.py pyproject.toml test/test_wiki_review.py uv.lock
git commit -m "feat(wiki-review): kb-wiki-review CLI entry point

argparse dispatcher for 5 subcommands (list, promote, approve, reject,
ttl-sweep). Interactive feedback prompt when --feedback flag omitted.
KST-anchored dates for User Feedback line prefixes and rejected_at
timestamps.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: TTL cron wrapper

**Files:**
- Create: `scripts/cron/kb-wiki-ttl-sweep.sh`

- [ ] **Step 1: Create the wrapper script**

Create `scripts/cron/kb-wiki-ttl-sweep.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$KB_ROOT/.cron/logs"
LOCK_DIR="$KB_ROOT/.cron/locks"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

if ! flock -n "$LOCK_DIR/wiki-ttl-sweep.lock" \
    bash -lc "cd '$KB_ROOT' && uv run kb-wiki-review ttl-sweep --days 7" \
    >> "$LOG_DIR/wiki-ttl-sweep.log" 2>&1; then
  echo "[$(date -Iseconds)] ERROR: kb-wiki-ttl-sweep failed" >&2
  exit 1
fi
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/cron/kb-wiki-ttl-sweep.sh
```

- [ ] **Step 3: Verify shellcheck (if available) or basic syntax**

Run: `bash -n scripts/cron/kb-wiki-ttl-sweep.sh`
Expected: no output (syntax OK).

- [ ] **Step 4: Commit (outer repo)**

```bash
cd /home/spow12/codes/KnowledgeBase
git add scripts/cron/kb-wiki-ttl-sweep.sh
git commit -m "feat(cron): TTL sweep wrapper for kb-wiki-review

Wraps 'kb-wiki-review ttl-sweep --days 7' with flock and log rotation,
matching the pattern used by daily report wrappers. Schedule manually
via crontab: '30 0 * * * /path/to/scripts/cron/kb-wiki-ttl-sweep.sh'.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: Operator manual + CLAUDE.md updates

**Files:**
- Create: `docs/workflows/wiki-approval-workflow.md`
- Modify: `CLAUDE.md` (outer)

- [ ] **Step 1: Create the operator manual**

Create `docs/workflows/wiki-approval-workflow.md`:

```markdown
# Wiki Approval Workflow

AI 작성 wiki 페이지에 사람 검토 단계를 도입하는 워크플로우.
관련 spec: `docs/superpowers/specs/2026-05-19-wiki-approval-workflow-design.md`.

## Status Model

| Status | 의미 | 다음 상태 |
|---|---|---|
| `not_processed` | AI가 막 작성 — daily-update agent가 아직 안 본 상태 | promote → pending_for_approve, 또는 7d TTL → rejected |
| `pending_for_approve` | 사용자 검토 대기 | approve → approved, reject → rejected (wiki 밖 이동) |
| `approved` | 정식 wiki 콘텐츠 (INDEX.md / subject hub 노출) | 의미 편집 시 not_processed로 self-reset |

## Scope

In-scope page types: `entity`, `concept`, `decision`, `improvement`, `checklist`, `question`.
Out of scope: `summary` (자동 생성), `index`.

## CLI

```
uv run kb-wiki-review list [--status pending_for_approve|not_processed|approved|all] [--counts]
uv run kb-wiki-review promote <stem>                 # daily-update agent용
uv run kb-wiki-review approve <stem> [--feedback "..."]
uv run kb-wiki-review reject  <stem> [--feedback "..."]
uv run kb-wiki-review ttl-sweep [--days 7]           # cron only
```

Empty `--feedback` (또는 interactive prompt에서 enter만) → User Feedback 라인 미추가.

## Daily-update agent contract

MVP에서 별도 cron 없음. 사용자가 Claude Code 세션에서 수동 invoke.

1. Input:
   ```bash
   uv run kb-wiki-review list --status not_processed
   ```
2. 각 페이지에 대해 LLM 판단:
   - 소스가 명확하고 검증 가능한가?
   - 다른 wiki/handoff에서 참조될 가능성이 있는가?
   - 이벤트 dump가 아닌 *지식*인가 (시간이 지나도 가치 유지)?
3. Promote:
   ```bash
   uv run kb-wiki-review promote <stem>
   ```
4. Leave: 아무것도 안 함. 다음 날 재고려. 7일째 자동 TTL.

**금지**: agent는 직접 reject 안 함. 사람만 reject. TTL이 deterministic 안전망.

## TTL cron

`scripts/cron/kb-wiki-ttl-sweep.sh` 가 매일 00:30 KST 실행 권장:

```cron
30 0 * * * /home/spow12/codes/KnowledgeBase/scripts/cron/kb-wiki-ttl-sweep.sh
```

`created` 가 7일 이전인 `not_processed` 페이지를 자동 reject (rejected_by=auto_ttl).

## Approved 페이지 수정 정책

- Semantic 변화 (사실 변경, 새 정보 추가, 결론 수정): `review_status: not_processed` 로 self-reset. 다음 daily-update에서 재promote 후보.
- Typo / 포매팅: status 유지.

Deterministic 감지 없음. CLAUDE.md 가이드라인 + agent 판단에 의존.

## Subject `_index.md` hub

Approve 후 사용자(또는 agent)가 subject hub에 `- [[<stem>]]` 라인 수동 추가. Lint가 missing entry를 warning으로 알려줌. 자동 동기화는 별도 작업.

## Rejected 파일 보존

거절된 페이지는 `data/rejected/<원래 wiki path>` 로 git mv. Wiki 트리 깨끗, audit 데이터는 패턴 분석용으로 보존. `data/rejected/` 는 lint scope 밖.

## Walkthrough

자세한 happy/reject/TTL/edit 시나리오는 spec §10 참고.
```

- [ ] **Step 2: Update outer CLAUDE.md**

Open `CLAUDE.md` (outer repo root). Add a new section after the existing "Important Rules" section:

```markdown
## Wiki Approval Workflow

6 wiki 페이지 타입(`entity`, `concept`, `decision`, `improvement`, `checklist`, `question`)은 `review_status` 필드를 통한 사람 승인 사이클을 거친다.

- **새 페이지 작성 (AI)**: 템플릿이 `review_status: not_processed` 를 자동 포함. AI가 직접 추가/수정할 필요 없음.
- **Approved 페이지 수정 (AI)**: semantic 변화면 `review_status` 를 `not_processed` 로 self-reset, typo/포매팅이면 유지. Deterministic 감지는 없음 — agent 판단.
- **`## User Feedback` 헤딩 예약**: CLI 전용 섹션. 일반 콘텐츠에서 이 정확한 헤딩 사용 금지. 다른 의미는 `## Feedback`, `## Reviewer Notes` 등 다른 이름 사용.
- **INDEX.md / subject `_index.md`**: 자동 동기화 없음. Approve 후 subject hub 라인 추가는 user 또는 동반 작업 agent의 책임.
- **CLI**: `uv run kb-wiki-review list / promote / approve / reject / ttl-sweep`. 상세는 `docs/workflows/wiki-approval-workflow.md`.

`improvement` 타입은 두 `_status` 필드를 보유: `review_status`(이 페이지가 승인됐는가)와 `issue_status`(추적 이슈가 open/resolved 등). 같은 prefix가 도메인을 분리.
```

- [ ] **Step 3: Update Documentation list in CLAUDE.md**

In the existing "Documentation" section of `CLAUDE.md`, add a new line:

```markdown
- [Wiki Approval Workflow](docs/workflows/wiki-approval-workflow.md) — review_status lifecycle, CLI, TTL cron
```

- [ ] **Step 4: Commit (outer repo)**

```bash
cd /home/spow12/codes/KnowledgeBase
git add docs/workflows/wiki-approval-workflow.md CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: wiki approval workflow operator manual

Adds docs/workflows/wiki-approval-workflow.md as the day-to-day guide
for users and agents working with the new review lifecycle, and updates
CLAUDE.md with the high-level rules (review_status field, edit policy,
Reserved User Feedback heading, subject hub update responsibility,
improvement's two _status fields).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Migration — populate review_status on existing pages + INDEX regen

**Files:**
- Modify (data nested repo): all `data/wiki/**/*.md` of 6 in-scope types
- Modify (data nested repo): `data/wiki/INDEX.md`

This task runs ON the developer's machine after Tasks 1–14 land. It is **NOT** a permanent piece of code — the migration script lives only inside this plan (and the spec).

- [ ] **Step 1: Confirm baseline state**

```bash
cd /home/spow12/codes/KnowledgeBase
uv run kb-lint-wiki 2>&1 | tail -20
```

Expected: errors reporting missing `review_status` on the 5 in-scope pages (entities + improvement + decision + concept). This is the gap migration will close.

- [ ] **Step 2: Run the migration script**

```bash
cd /home/spow12/codes/KnowledgeBase
uv run python - <<'PYEOF'
import re
from pathlib import Path

TYPES = {"entity", "concept", "decision", "improvement", "checklist", "question"}

for p in Path("data/wiki").rglob("*.md"):
    text = p.read_text()
    if not text.startswith("---"):
        continue
    parts = text.split("---", 2)
    if len(parts) < 3:
        continue
    fm, body = parts[1], parts[2]
    m = re.search(r"^type:\s*(\w+)", fm, re.MULTILINE)
    if not m or m.group(1) not in TYPES:
        continue
    type_name = m.group(1)

    changed = False

    if "review_status" not in fm:
        fm = fm.rstrip() + "\nreview_status: pending_for_approve\n"
        changed = True

    if type_name == "improvement" and re.search(r"^status:", fm, re.MULTILINE):
        fm = re.sub(r"^status:", "issue_status:", fm, flags=re.MULTILINE)
        changed = True

    if changed:
        p.write_text(f"---{fm}---{body}")
        print(f"migrated {p}")
PYEOF
```

Expected output: one "migrated …" line per in-scope page (≈5 files).

- [ ] **Step 3: Verify rename happened on improvement page**

```bash
grep -n "^status:\|^issue_status:" data/wiki/improvements/2026-05/KB_Usage_Report_Restructure_Blockers.md
```

Expected: `issue_status: open`. No bare `status:` line.

- [ ] **Step 4: Verify review_status populated on all in-scope pages**

```bash
grep -L "^review_status:" data/wiki/entities/*/2026-*/*.md data/wiki/concepts/*.md data/wiki/decisions/*.md data/wiki/improvements/*/*.md 2>/dev/null
```

Expected: empty output (every in-scope page now has review_status).

- [ ] **Step 5: Regenerate INDEX.md (approved-only filter)**

```bash
uv run kb-wiki-index
```

Expected: writes INDEX.md. After migration all in-scope pages are `pending_for_approve`, so INDEX will list only the out-of-scope summary pages (and nothing under Entities/Concepts/Decisions/Improvements until user approves).

- [ ] **Step 6: Run full lint, verify 0 errors**

```bash
uv run kb-lint-wiki
```

Expected: PASSED with 0 errors. Warnings about subject `_index.md` listing approved pages should be gone (because no approved pages yet). Some orphan warnings on summary pages may remain — those are pre-existing.

- [ ] **Step 7: Verify CLI list works on live data**

```bash
uv run kb-wiki-review list --counts
```

Expected: `<n> pending_for_approve, 0 not_processed, 0 approved` (n = number of migrated pages).

```bash
uv run kb-wiki-review list
```

Expected: tabular listing of all pending pages (the migrated ones).

- [ ] **Step 8: Commit (data nested repo)**

```bash
cd /home/spow12/codes/KnowledgeBase/data
git add wiki/
git commit -m "$(cat <<'EOF'
migrate: add review_status to existing wiki pages

Bulk-marks all in-scope wiki pages as pending_for_approve so user can
review them one by one via kb-wiki-review. Improvement page's bare
'status' field is also renamed to 'issue_status' to align with the
new naming convention. INDEX.md regenerated under the approved-only
filter (now empty for in-scope sections until user approves).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 9: Final end-to-end verification**

```bash
cd /home/spow12/codes/KnowledgeBase
uv run kb-lint-wiki --check-immutability
uv run pytest test/ -v
```

Expected: lint PASSED 0 errors; pytest all PASS (existing + new test files: test_lint_wiki, test_wiki_index, test_wiki_review).

---

## Done — Summary of Outcomes

After all 15 tasks:

- **Outer repo** has 14+ commits covering: validators, lint, index, sync, templates, store/feedback/commands helpers, CLI entry, pyproject script entry, TTL cron wrapper, operator manual, CLAUDE.md update.
- **Data nested repo** has 1 commit: migration of existing pages to `pending_for_approve` + improvement `status → issue_status` rename + INDEX.md regen.
- New CLI installed: `kb-wiki-review {list, promote, approve, reject, ttl-sweep}`.
- All existing tests still pass; new tests cover the new behavior in `test_wiki_review.py`, `test_lint_wiki.py`, `test_wiki_index.py`.

User next actions:
1. `uv run kb-wiki-review list` and process the migrated queue page-by-page.
2. Optionally register the TTL sweep cron (`30 0 * * * scripts/cron/kb-wiki-ttl-sweep.sh`).
