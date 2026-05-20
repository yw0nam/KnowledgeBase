---
name: memory-report
description: Use when running the daily, weekly, or monthly memory workflow — discovering period sources, writing summary + worthy wiki pages, writing the period handoff, and lint-clean uncommitted output. Covers raw discovery, period dispatch (daily/weekly/monthly), wiki page frontmatter, lint ordering, and canonical lint failures. Also covers the legacy workflow name memory_report.
---

# memory-report

## Overview

One skill, three periods. The agent receives a target (`YYYY-MM-DD`, `YYYY-WNN`, or `YYYY-MM`) and produces a period summary + zero-or-more wiki pages + one handoff, all lint-clean and uncommitted.

The shared half (Repo layout, wiki schemas, lint order, common failures) is identical across periods. The per-period half (source discovery, promotion intensity, output filename) differs and lives in three small sections below.

This SKILL replaces the doc-load pattern where each cron agent re-read 6 markdown files on every run.

**Bundled reference (self-contained — do not consult docs/ at runtime):**
- `reference/templates/{entity,concept,decision,question,improvement,checklist}.md` — period workflow copies remain here for backward compatibility
- `reference/templates/summaries/{weekly,monthly}.md` — weekly/monthly summary skeletons (daily summary schema is inlined below)

For new atomic wiki pages, import `wiki-authoring` as the canonical page-authoring contract. Handoff authoring is delegated to `handoff-document` — invoke that skill for the period handoff. This skill does not duplicate handoff schema.

If anything below contradicts the lint code (`src/kb_mcp/cli/wiki/validators.py`), the lint code wins — file an issue and update this skill.

## Period Dispatch — find your period BEFORE reading sections

| Period | Cron schedule (KST) | Target arg format | Lock file | Skill section |
|---|---|---|---|---|
| daily | `30 3 * * *` | `YYYY-MM-DD` | `daily.lock` | [§Daily](#daily) |
| weekly | `15 4 * * 1` | `YYYY-WNN` (ISO week) | `weekly.lock` | [§Weekly](#weekly) |
| monthly | `45 4 1 * *` | `YYYY-MM` | `monthly.lock` | [§Monthly](#monthly) |

If the cron prompt says "daily memory workflow for 2026-05-19", you're in §Daily. Read SHARED CONVENTIONS once, then jump to the matching period section.

## When to Use

- Any of the three crons fires
- Manual invocation: "Run the {daily|weekly|monthly} memory workflow for {target}"

**Do NOT use** for: wiki promotion (separate workflow), raw ingestion (manual / external scripts), or recovery from a previously failed run without reading the prior handoff first.

---

# Shared Conventions

## Repo Layout (memorize, don't re-discover)

```
data/
├── raw/
│   ├── github/                # GitHub CLAUDE.md + issues/PRs (flat — date in filename)
│   ├── gmail/{YYYY}/{MM}/     # date-partitioned
│   ├── sessions/{YYYY}/{MM}/  # date-partitioned
│   ├── web/                   # flat
│   └── ops/
│       ├── cron/{YYYY}/{MM}/  # cron-generated usage reports
│       ├── runs/{YYYY}/{MM}/
│       ├── decisions/{YYYY}/{MM}/
│       ├── traces/{YYYY}/{MM}/
│       └── ingest_state/      # state files, not source
├── handoffs/{YYYY}/{MM}/<task-slug>/
└── wiki/
    ├── entities/{subject}/{YYYY-MM}/
    ├── improvements/{YYYY-MM}/
    ├── concepts/              # FLAT (timeless ideas)
    ├── decisions/             # flat, filename prefixes date: 2026-05-18-foo.md
    ├── questions/             # flat
    ├── checklists/            # flat
    └── summaries/{YYYY}/{MM}/ # YYYY-MM-DD-memory.md, YYYY-WNN-weekly.md, YYYY-MM-monthly.md
```

`sources:` frontmatter paths are **relative to `data/`** (e.g. `wiki/summaries/...`, NOT `data/wiki/summaries/...`).

## Wiki Page Schemas (the only thing lint ERRORs you for)

All review-tracked types (`entity`, `concept`, `decision`, `improvement`, `checklist`, `question`) inherit `review_status: not_processed` from template. Don't manually set it to anything else.

### summary

```yaml
---
type: summary
subtype: daily | weekly | monthly
date: "YYYY-MM-DD"            # daily only
week: "YYYY-WNN"              # weekly only
period_start: "YYYY-MM-DD"    # weekly/monthly
period_end: "YYYY-MM-DD"      # weekly/monthly
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources:
  - wiki/summaries/YYYY/MM/...
  - handoffs/YYYY/MM/<task>/...
tags: []
---
```
Required: `type, created, updated, sources, tags` + the period-specific date fields. **No `review_status`** — summaries are exempt from approval.

### entity / concept / question

```yaml
---
type: entity                  # or concept, question
review_status: not_processed
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources: [...]
aliases: []                   # entity & concept only
tags: []
---
```

### improvement — **the lint trap**

```yaml
---
type: improvement
review_status: not_processed
kind: improvement             # one of: improvement | issue | proposal
observed_at: "YYYY-MM-DD"     # ISO date — required, lint validates format
domain: dx                    # one of: cost | correctness | perf | dx | security
severity: med                 # one of: low | med | high
issue_status: open            # one of: open | acknowledged | resolved | wontfix
related: []                   # list of wikilinks, lint resolves them
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources: [...]
tags: []
---
```

Missing any of `kind/observed_at/domain/severity/issue_status/related` → ERROR. Invalid enum → ERROR.

### decision

```yaml
---
type: decision
review_status: not_processed
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources: [...]
tags: [decision]
---
```
Filename convention: `YYYY-MM-DD-<slug>.md` (date prefix in filename, not folder).

### checklist

```yaml
---
type: checklist
review_status: not_processed
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources: [...]
tags: []
---
```
Body **must** contain `## Items` section with `- [ ] ...` task-list syntax. Lint enforces this.

## Lint Order — DO THIS, the past runs failed by skipping step 1

```bash
# 1. Regenerate INDEX.md before linting. Lint will ERROR with
#    "INDEX.md: stale" if you created a wiki page without regenerating.
uv run kb-wiki-index

# 2. Wiki lint
uv run kb-lint-wiki --check-immutability   # daily/weekly
uv run kb-lint-wiki --strict               # monthly (warnings → errors)

# 3. Handoff lint
uv run kb-lint-handoff
```

All lint commands must exit 0 (errors=0). Warnings are OK to leave (orphan/stub for not-yet-approved pages is normal).

## Common Lint Failures (preemptive fixes)

| ERROR pattern | Cause | Fix before lint |
|---|---|---|
| `INDEX.md: stale — run kb-wiki-index` | Created a wiki page, didn't regen index | Run `uv run kb-wiki-index` first |
| `source file not found: wiki/summaries/daily/...` | Cited a legacy path. Daily summaries live at `wiki/summaries/{YYYY}/{MM}/`, not `wiki/summaries/daily/` | Use the partitioned path |
| `source file not found: data/raw/...` | `sources:` paths must be relative to `data/`, not `data/data/` | Drop the `data/` prefix |
| `missing frontmatter field: kind` (improvement) | Used base template, didn't fill improvement-specific fields | All 6 extra fields required |
| `invalid domain: 'xxx'` | Domain not in enum | Use one of: cost, correctness, perf, dx, security |
| `raw file modified after creation (immutability violation)` | Someone (not you) edited a raw file | **Do not touch raw files.** Log in handoff §8; cannot be fixed by this run |
| `stub page — body N chars (< 100)` | WARN only, ignore | — |
| `orphan page — no inbound links` | WARN only, expected for new pages | — |

## Handoff (defer to `handoff-document`)

Every run writes one handoff. Use the `handoff-document` skill for filename grammar, frontmatter, body sections, and lint. This skill only specifies the **task folder name** and **content focus** per period (see each period section).

## Log Format (append to data/log.md, all periods)

```markdown

## YYYY-MM-DD ({period} memory build — target: {TARGET})

- **fill**: {TARGET} {period} synthesis
  - 소스: <list>
  - 출력: wiki/summaries/YYYY/MM/<output>.md (신규)
- **fill**: <new wiki pages, one per line>
- **handoff**: <handoff path>
- **lint**: kb-lint-wiki + kb-lint-handoff PASSED (errors 0, warnings N)
- Note: commit은 사용자가 수동으로 review 후 진행
```

## Workflow Discipline (all periods)

- **One target per run.** Never extend scope implicitly to "and also yesterday/last week".
- **Never edit raw files.** Immutability violations are external — log in handoff §8.
- **Do not auto-promote** wiki pages to `pending_for_approve` — that's the wiki-promote cron's job.
- **Do not git commit.** Wrapper contract is uncommitted handoff for manual review.
- **If blocked**, write the handoff with `status: ready`, list the blocker in §8, and exit non-zero.

---

# §Daily

**Target**: `YYYY-MM-DD` (yesterday).
**Output summary**: `data/wiki/summaries/{YYYY}/{MM}/{TARGET}-memory.md`
**Handoff folder**: `data/handoffs/{YYYY}/{MM}/wiki-daily-build/`
**Promotion intensity**: triage > restructure. Prefer summary; create wiki pages only when source has clear future value.

## Daily Step 0: Identify yesterday's raw — single command, no tree walking

```bash
TARGET="$1"                          # e.g. 2026-05-19
YEAR="${TARGET%%-*}"
MONTH=$(echo "$TARGET" | cut -d- -f2)

find data/raw -type f -name "*.md" \
  \( -path "*/$YEAR/$MONTH/*" -o -name "${TARGET}*" \) \
  -not -name ".gitkeep" | sort

# Active task handoffs this month + only the ready ones
ls data/handoffs/$YEAR/$MONTH/*/  2>/dev/null
grep -lr "status: ready" data/handoffs/$YEAR/$MONTH/
```

Do NOT walk `data/raw/<subdir>` directory-by-directory.

## Daily Workflow (9 steps)

```
1. Run Daily Step 0 → raw set + active handoffs for TARGET
2. Read prior wiki-daily-build handoff (status: ready) for context
3. Write data/wiki/summaries/{Y}/{M}/{TARGET}-memory.md
4. Create only obviously-worthy entity/improvement/concept pages
   — leave uncertain items in handoff "Promotion Candidates"
5. Mark prior daily handoff status: consumed IF its open items were handled
6. Write new handoff via `handoff-document` under wiki-daily-build/
7. Append to data/log.md
8. Run Lint Order (kb-wiki-index → kb-lint-wiki --check-immutability → kb-lint-handoff)
9. STOP. Do NOT git commit.
```

## Daily promotion intensity

Prefer summary + triage. Create atomic pages only when source has clear future value. Uncertain → handoff's §10 Promotion Candidates, not a new page.

---

# §Weekly

**Target**: `YYYY-WNN` (last ISO week, e.g. `2026-W20`).
**Output summary**: `data/wiki/summaries/{YYYY}/{MM}/{TARGET}-weekly.md` (where MM = month of week's end)
**Template**: `reference/templates/summaries/weekly.md`
**Handoff folder**: `data/handoffs/{YYYY}/{MM}/wiki-weekly-build/`
**Promotion intensity**: patterns over events. Promote signals **repeated across ≥2 days** or strongly supported by one important source.

## Weekly Step 0: collect the week's daily summaries and handoffs

```bash
TARGET="$1"                          # e.g. 2026-W20
# Resolve ISO week → Monday date and Sunday date
PERIOD_START=$(date -d "$(echo $TARGET | sed 's/-W/ /')-1" +%F 2>/dev/null \
               || date -d "${TARGET%-W*}-01-01 +$((10#${TARGET#*-W} * 7 - 7)) days" +%F)
PERIOD_END=$(date -d "$PERIOD_START +6 days" +%F)

# Daily memory summaries falling in the week
for d in $(seq 0 6); do
  D=$(date -d "$PERIOD_START +$d days" +%F)
  ls data/wiki/summaries/${D%-*-*}/${D#*-}/${D}-memory.md 2>/dev/null
done

# Ready handoffs from wiki-daily-build for the period
grep -l "status: ready" data/handoffs/*/*/wiki-daily-build/*.md 2>/dev/null
```

Sanity check: expect 7 daily memory files. Document any missing day in the handoff §8; do not synthesize phantom days.

## Weekly Workflow (10 steps)

```
1. Run Weekly Step 0 → seven daily summaries + ready daily handoffs
2. Read prior wiki-weekly-build handoff (status: ready) if any
3. Write data/wiki/summaries/{Y}/{M}/{TARGET}-weekly.md using reference/templates/summaries/weekly.md
4. Promote repeated patterns into concepts, improvements, checklists, or decisions
   (see Weekly promotion intensity below)
5. Mark consumed daily handoffs as status: consumed ONLY for items actually handled
6. Write new handoff via `handoff-document` under wiki-weekly-build/
7. Note monthly candidates in handoff §10 (which patterns are monthly-worthy)
8. Append to data/log.md
9. Run Lint Order (kb-wiki-index → kb-lint-wiki --check-immutability → kb-lint-handoff)
10. STOP. Do NOT git commit.
```

## Weekly promotion intensity

- **Promote** when signal repeats across multiple days or has one strong-source support.
- Convert recurring operational mistakes → **checklist** candidates.
- Convert unresolved-but-actionable work → **improvements**.
- Convert closed architectural/workflow choices → **decisions** (only if rationale is captured).
- Don't promote single-day mentions unless source is high-value.

---

# §Monthly

**Target**: `YYYY-MM` (last month).
**Output summary**: `data/wiki/summaries/{YYYY}/{MM}/{TARGET}-monthly.md`
**Template**: `reference/templates/summaries/monthly.md`
**Handoff folder**: `data/handoffs/{YYYY}/{MM}/wiki-monthly-maintenance/`
**Promotion intensity**: cleanup > add. Consolidate duplicates, close stale, promote stable procedures.

## Monthly Step 0: collect weekly summaries and prior monthly handoff

```bash
TARGET="$1"                          # e.g. 2026-05
YEAR="${TARGET%-*}"
MONTH="${TARGET#*-}"

# Weekly summaries within the month
ls data/wiki/summaries/$YEAR/$MONTH/*-weekly.md 2>/dev/null

# Prior monthly maintenance handoffs (ready status only)
grep -l "status: ready" data/handoffs/*/*/wiki-monthly-maintenance/*.md 2>/dev/null

# Cleanup signal — orphan/stub pages flagged by lint
uv run kb-lint-wiki 2>&1 | grep -E "orphan page|stub page" | head -20
```

## Monthly Workflow (11 steps)

```
1. Run Monthly Step 0 → weekly summaries + ready monthly handoff + cleanup signals
2. Review duplicate concepts (same idea, different page), stale improvements
   (issue_status: open but observed_at > 30 days ago), open decision candidates
3. Write data/wiki/summaries/{Y}/{M}/{TARGET}-monthly.md using reference/templates/summaries/monthly.md
4. Consolidate duplicated concepts ONLY when sources support the merge
   (different evidence → keep both; same evidence → merge with combined sources)
5. Close or defer stale improvements: set issue_status to resolved/wontfix with rationale,
   OR leave open and note the blocker
6. Promote stable repeated procedures into checklists
7. Mark consumed weekly handoffs as status: consumed for items handled
8. Write monthly handoff via `handoff-document` under wiki-monthly-maintenance/
   — flag reusable automation as promotion: skill_candidate
9. Append to data/log.md
10. Run Lint Order with --strict (warnings → errors): kb-wiki-index → kb-lint-wiki --strict → kb-lint-handoff
11. STOP. Do NOT git commit.
```

## Monthly promotion intensity

- **Prefer cleanup** over new pages. Don't add fresh content the weekly should have caught.
- **Don't merge pages** if source evidence differs in meaning — separate facts deserve separate pages.
- **Mark reusable automation patterns** as `promotion: skill_candidate` in handoff §10. Don't write the skill in this run; flag it for the user.
- **Leave human-decision items open** rather than turning them into ADRs. Decisions are user-driven, not synthesized.

---

# Red Flags — STOP and re-check

- About to `Read data/raw/<subdir>` for the 3rd time → use Step 0 find command for your period
- About to create a wiki page but haven't checked `sources:` path is `data/`-relative → check before lint
- About to write improvement page from `reference/templates/improvement.md` without filling the 6 extra fields → fill them or downgrade to entity/concept
- About to run `kb-lint-wiki` without first running `kb-wiki-index` → run index first
- About to `git commit` → STOP. None of the three crons commit; wrapper contract is uncommitted handoff for manual review
- Lint ERRORs on raw immutability → not your run's fault, log it in handoff §8 and PASS the run
- About to mix periods in one run (e.g. "and also catch up last week's") → STOP. Run one period at a time
- Weekly run with <7 daily summaries → document missing days in handoff; do not synthesize phantom days
- Monthly run with no weekly summaries → STOP. Weekly must run first; write a handoff explaining and exit
