---
name: cron-wrapup
description: Use when running the nightly KB cron wrap-up — aggregating the previous day's usage reports, memory page, wiki-promote / TTL outcomes, and `data/raw/ops/cron/` per-run log exit states into a single durable Slack-digest-stable wiki summary plus run handoff.
---

# cron-wrapup

## DB-Canonical Override

DB rows are the source of truth. Write the wrap-up summary, run handoff,
operation log, and cron run log through the HTTP DB API with
`Authorization: Bearer $KB_API_TOKEN`. Markdown under `data/` is generated
export. If any older instruction below says to lint as a
write gate, commit `data/`, or call `data-sync`, ignore that instruction and use
the DB API instead.

## Overview

One skill, one job: at 05:00 KST, after the night's pipeline has finished, produce a deterministic operational snapshot of what the KB cron jobs did and what the user needs to notice. The output is the single source of truth for the 09:00 Slack digest — Slack must never read memory pages directly.

Two artefacts per run:

1. **Wiki summary** — `data/wiki/summaries/{YYYY}/{MM}/{TARGET}-cron-wrapup.md` (`type: summary`, `subtype: cron-daily`). Body uses fixed H2 section names (`Status`, `Jobs`, `Insights`, `Action Items`, `Anomalies`, `Counters`, `Links`) so downstream parsers stay stable as prose evolves.
2. **Run handoff** — `data/handoffs/{YYYY}/{MM}/cron-wrapup/{TARGET}_{role}_handoff_NN.md` via the `handoff-document` skill.

This skill is the **operational command layer**. Content synthesis (what happened in the world) lives in `memory-report`'s daily memory page — do not duplicate it here. Wrap-up describes what happened in the KB *pipeline* and extracts the small set of user-facing insights and follow-up actions created by that pipeline.

**Bundled reference (self-contained — do not consult docs/ at runtime):**

- `reference/templates/cron-wrapup-summary.md` — wiki summary skeleton with seven canonical H2 sections pre-filled with placeholder rows. Copy this verbatim and fill cells.

For handoff authoring, import `handoff-document`. This skill does not duplicate the handoff schema.

If anything below contradicts the lint code (`src/kb/lint/wiki.py`), the lint code wins — file an issue and update this skill.

## When to Use

- Daily 05:00 KST cron fires via `scripts/cron/kb-cron-wrapup.sh`.
- Manual invocation: "Run the KB cron wrap-up for {YYYY-MM-DD}".

**Do NOT use** for:

- Content synthesis — use `memory-report` (daily memory page).
- Wiki promotion — use `wiki-approval` (separate cron).
- Raw ingestion — manual or external scripts only; never the wrap-up.
- Re-validating the whole KB history or using lint as analysis input. The wrap-up runs the required lint gate only after writing its own summary/handoff.

## Target

`TARGET = YYYY-MM-DD` (yesterday in KST). The cron wrapper supplies this:

```bash
TARGET_DATE="$(TZ=Asia/Seoul date -d 'yesterday' +%F)"
```

If the user manually invokes "Run the KB cron wrap-up for 2026-05-20", `TARGET = 2026-05-20`. Never default to "today" — the night's pipeline writes for yesterday.

## Repo Layout (the inputs the wrap-up reads)

```
data/
├── wiki/summaries/{YYYY}/{MM}/            # Exported markdown; or read pages via psql (see state-db-schema-reference)
│   ├── {TARGET}-opencode-usage.md         # DB-backed (kb-opencode-daily-report posts to DB API)
│   ├── {TARGET}-claude-code-usage.md      # DB-backed
│   ├── {TARGET}-hermes-usage.md           # DB-backed
│   └── {TARGET}-memory.md                 # DB-backed (kb-memory-daily posts to DB API)
├── handoffs/{YYYY}/{MM}/
│   ├── wiki-daily-build/{TARGET}_*_handoff_*.md   # run handoff for memory-daily
│   └── wiki-promote/...                            # if wiki-promote ran (folder per wiki-approval)
├── raw/ops/cron/{YYYY}/{MM}/              # per-run cron log files (one file per job per target)
│   ├── {TARGET}_kb-opencode-daily-report.log
│   ├── {TARGET}_kb-claude-code-daily-report.log
│   ├── {TARGET}_kb-hermes-daily-report.log
│   ├── {TARGET}_kb-memory-daily.log
│   ├── {TARGET}_kb-wiki-ttl-sweep.log
│   ├── {TARGET}_kb-wiki-promote.log
│   ├── {TARGET}_kb-memory-weekly.log       # exists on Monday (after weekly run for prior ISO week)
│   └── {TARGET}_kb-memory-monthly.log      # exists on day 1 (after monthly run for prior month)
│   └── {TARGET}_kb-cron-wrapup.log         # committed by the shell wrapper AFTER session exits
└── log.md
```

> **Note:** `{TARGET}_kb-cron-wrapup.log` does not exist inside `data/` while the session is running.
> The shell wrapper submits it through `POST /api/cron-runs` after the session exits.
> Do not read or stage it during the session.

`sources:` frontmatter paths are **relative to `data/`** (e.g. `wiki/summaries/...`, NOT `data/wiki/summaries/...`).

Every wrapper uses `TARGET_DATE` (= yesterday in KST) as the filename prefix, even when its workflow target is a week or month — so the daily wrap-up's glob `{TARGET}_*.log` matches every wrapper that ran in last night's pipeline. The actual weekly/monthly period stays in the log body and the produced wiki page.

Each run writes its own immutable log file, so the wrap-up reads exactly one file per job per target — no time-window grep required.

## Wiki Summary Schema (the only thing lint ERRORs you for)

```yaml
---
type: summary
subtype: cron-daily
date: "YYYY-MM-DD"            # the TARGET
created: "YYYY-MM-DD"         # the run date (today in KST)
updated: "YYYY-MM-DD"
sources:
  - wiki/summaries/YYYY/MM/{TARGET}-memory.md
  - wiki/summaries/YYYY/MM/{TARGET}-opencode-usage.md
  - wiki/summaries/YYYY/MM/{TARGET}-claude-code-usage.md
  - wiki/summaries/YYYY/MM/{TARGET}-hermes-usage.md
  - handoffs/YYYY/MM/wiki-daily-build/{TARGET}_*_handoff_*.md
  # plus handoffs/YYYY/MM/wiki-promote/... if wiki-promote produced output that day
tags: [cron-wrapup, ops-daily]
---
```

Required: `type, created, updated, sources, tags, date`. **No `review_status`** — summaries are exempt from approval. `subtype: cron-daily` is currently free-form (lint does not enforce subtype values) but use it consistently.

## Body Contract (Slack-digest-stable — DO NOT rename sections)

The seven H2 sections below are the parsing contract for the 09:00 Slack digest. Section names, order, and column shapes must remain stable. Authors may add prose under each section but must not rename or reorder them.

```markdown
# Cron Wrap-up — {TARGET}

## Status

OK | DEGRADED | FAILED

(One-word verdict on the first line, optional one-sentence elaboration on the second.)

## Jobs

| Job | Schedule | Exit | Output | Notes |
| --- | --- | --- | --- | --- |
| kb-opencode-daily-report   | 10 3 * * *  | 0   | wiki/summaries/2026/05/2026-05-20-opencode-usage.md   | 1 session, 1.05 USD |
| kb-claude-code-daily-report| 20 3 * * *  | 0   | wiki/summaries/2026/05/2026-05-20-claude-code-usage.md| 10/14 sessions, 69.77 USD |
| kb-hermes-daily-report     | 15 3 * * *  | 0   | wiki/summaries/2026/05/2026-05-20-hermes-usage.md     | 3 sessions, zombie 0 |
| kb-memory-daily            | 30 3 * * *  | 0   | wiki/summaries/2026/05/2026-05-20-memory.md           | 2 new pages |
| kb-wiki-ttl-sweep          | 30 0 * * *  | 0   | (log only)                                            | 0 pages expired |
| kb-wiki-promote            | 0 4 * * *   | 0   | handoffs/2026/05/wiki-promote/...                     | 1 promoted |

Exactly 5 columns. Missing jobs (e.g. weekly on non-Monday) → omit the row, do not invent.

## Insights

- none

(Extract 1-5 user-facing signals from the daily memory page, usage reports, and run handoffs. Prefer durable or decision-relevant signals: new improvement pages, recurring error trends, cost spikes, completed work that needs review, newly blocked work, or promotion candidates. Use the literal line `- none` only when the KB produced no meaningful new signal.)

## Action Items

| Priority | Owner | Item | Source |
| --- | --- | --- | --- |
| high | user | Review frontend-review-console PR #20 CI and merge readiness | wiki/summaries/2026/05/2026-05-20-memory.md |

(Extract concrete follow-ups from daily memory `Open Items`, `Next Run Notes`, run handoff `Next handoff instructions`, and unresolved improvement pages. Use owner `user`, `agent`, or `unknown`. If empty, use one row with `none | none | none | none`.)

## Anomalies

- none

(Or bullet list of issues: non-zero exits, missing inputs, lint failures, lock skips, late starts > 10 min. Use the literal line `- none` when empty — never delete the section.)

## Counters

| Metric | Value |
| --- | --- |
| pages_created       | 2 |
| pages_promoted      | 1 |
| pages_ttl_swept     | 0 |
| insights_count      | 5 |
| action_items_count  | 3 |
| lint_errors         | 0 |
| lint_warnings       | 12 |
| total_usd           | 70.82 |
| sessions_total      | 14 |

Keep snake_case keys so the digest can match on them. `insights_count` and `action_items_count` make an empty-looking status easy to detect even when jobs all succeeded.

## Links

- memory:    `wiki/summaries/2026/05/2026-05-20-memory.md`
- opencode:  `wiki/summaries/2026/05/2026-05-20-opencode-usage.md`
- claude:    `wiki/summaries/2026/05/2026-05-20-claude-code-usage.md`
- hermes:    `wiki/summaries/2026/05/2026-05-20-hermes-usage.md`
- daily-handoff: `handoffs/2026/05/wiki-daily-build/2026-05-20_opencode_handoff_04.md`
- promote-handoff: `handoffs/2026/05/wiki-promote/...`   (omit line if absent)
```

## Status Verdict — deterministic rules

Compute in this order; the first match wins:

| Verdict | Condition |
|---|---|
| `FAILED`   | Any cron wrapper exited non-zero **OR** any *required* input is missing (memory page, all three usage reports). |
| `DEGRADED` | Any non-blocking anomaly: lint warnings appearing today that weren't there yesterday, lock skip, optional input missing (promote handoff on a day promote was supposed to run), or a per-run log file file-mtime far past its scheduled cron time. |
| `OK`       | All expected logs show clean exit; Anomalies list is `- none`. |

Late-start detection: per-run logs do not contain wrapper-side start timestamps, so use the log file's mtime (or first content line's timestamp if the underlying tool emits one) versus the scheduled cron time. Treat slips > 10 min as DEGRADED only when the signal is clearly available; otherwise omit the anomaly rather than guess.

## Inputs the wrap-up reads — and what to extract from each

| Input | Extract |
|---|---|
| `wiki/summaries/{Y}/{M}/{T}-opencode-usage.md`     | sessions, total USD (DB metrics via API, or frontmatter/table from export) |
| `wiki/summaries/{Y}/{M}/{T}-claude-code-usage.md`  | sessions, USD, tool_error_rate, hot files count (DB metrics via API) |
| `wiki/summaries/{Y}/{M}/{T}-hermes-usage.md`       | sessions, zombie count |
| `wiki/summaries/{Y}/{M}/{T}-memory.md`             | path, key events, promotion candidates, open items, next-run notes; **do not copy the whole narrative** |
| `handoffs/{Y}/{M}/wiki-daily-build/{T}_*_handoff_*.md` | path, new pages count from §6 Outputs, risks, next handoff instructions |
| `handoffs/{Y}/{M}/wiki-promote/...`                | promoted count, rejected count, expired count |
| `raw/ops/cron/{Y}/{M}/{T}_kb-wiki-ttl-sweep.log`   | swept count + exit code |
| `raw/ops/cron/{Y}/{M}/{T}_*.log` (every per-run file matching this target — there is no `kb-cron-wrapup.log` in this folder) | non-zero exit lines, `ERROR:` lines, `Lock` skip lines |

Read each input at most once. Never use lint as a discovery source, never re-render existing summaries. The wrap-up MUST NOT read `data/raw/` other than `raw/ops/cron/{Y}/{M}/{TARGET}_*.log`. The wrap-up may extract concise insights/actions from the daily memory and handoffs, but must not duplicate the memory page's full content narrative.

## DB Write Order

1. Submit the wrap-up summary through `POST /api/pages`.
2. Submit the handoff through `POST /api/handoffs`.
3. Submit the operation note through `POST /api/operation-logs`.
4. Confirm every response reports `export.status: success`.

## Common Lint Failures (preemptive fixes)

| ERROR pattern | Cause | Fix before lint |
|---|---|---|
| `source file not found: wiki/summaries/...` | Cited a path that wasn't actually produced (e.g. promote handoff on day promote didn't run) | Drop the source line or change the path |
| `source file not found: data/wiki/...` | `sources:` paths must be `data/`-relative, not `data/data/` | Drop the `data/` prefix |

## Handoff (defer to `handoff-document`)

Every run writes one handoff. Use the `handoff-document` skill for filename grammar, frontmatter, body sections, and lint.

This skill specifies only:

- **Task folder**: `data/handoffs/{YYYY}/{MM}/cron-wrapup/` (one folder for the task; per-role NN keeps incrementing across dates, same shape as `wiki-daily-build/`).
- **Subject**: `{TARGET}` (the date being wrapped up).
- **Role**: whoever the cron wrapper invokes (currently `opencode`).
- **Content focus**: link to the produced wiki summary, list anomalies, set `status: ready` and a clear `## 9. Next handoff instructions` block for the next day or for the 09:00 digest.

## Log Format (submit through `POST /api/operation-logs`)

```markdown

## YYYY-MM-DD (cron wrap-up — target: {TARGET})

- **fill**: {TARGET} cron wrap-up summary
  - 소스: wiki/summaries/Y/M/{TARGET}-{opencode,claude-code,hermes}-usage.md, wiki/summaries/Y/M/{TARGET}-memory.md, raw/ops/cron/Y/M/{TARGET}_*.log
  - 출력: wiki/summaries/Y/M/{TARGET}-cron-wrapup.md (신규)
- **handoff**: handoffs/Y/M/cron-wrapup/{TARGET}_{role}_handoff_NN.md
- **db_write**: summary + handoff + operation log exported successfully
```

## Workflow (8 steps)

```
1. Resolve TARGET = yesterday in KST (or accept explicit argument)
2. Locate inputs: 3 usage pages, memory page, daily handoff, promote handoff (optional),
   per-run cron logs at `raw/ops/cron/{Y}/{M}/{TARGET}_*.log`. Note any MISSING required input → Status: FAILED later.
3. Extract per-input metrics (see Inputs table). Compute Counters.
4. Read every `raw/ops/cron/{Y}/{M}/{TARGET}_*.log` except `{TARGET}_kb-cron-wrapup.log` — that file does not exist during the session (the shell wrapper writes and commits it after the session exits, so it is never available to read here)
   for non-zero exits, ERRORs, lock skips. Collect into Anomalies.
5. Compute Status verdict (FAILED > DEGRADED > OK, first match wins).
6. Fill `reference/templates/cron-wrapup-summary.md` and submit it through `POST /api/pages` with export path `wiki/summaries/{Y}/{M}/{TARGET}-cron-wrapup.md`.
7. Write run handoff via `POST /api/handoffs` (subject = TARGET, role = invoker, status: ready).
8. Append the operation note via `POST /api/operation-logs`.
9. Confirm every response reports `export.status: success`.
10. STOP. Do NOT commit or push `data/`; it is generated export.
```

## Data Persistence Policy

DB rows are the durable checkpoint. Markdown, handoff files, `log.md`, and cron
logs under `data/` are generated export. Never stage, commit, or push from this workflow.

## Idempotency

- If `{TARGET}-cron-wrapup.md` already exists, **overwrite it** (the cron may rerun after a failure). Update `updated:` to today.
- For the handoff, use the next per-role `NN` in `handoffs/{Y}/{M}/cron-wrapup/`. Do not overwrite a prior handoff.

## Failure path

If a required input is missing (e.g. memory page never wrote):

1. Still write the wrap-up. Set `Status: FAILED`.
2. List the missing input as a bullet under `## Anomalies`.
3. In the run handoff, set `status: ready` and put the failure cause in `§8. Risks / uncertainties` with a clear escalation note for §9 so the 09:00 digest surfaces it to Slack.
4. Exit non-zero from the wrapper so the cron log records the failure.

## Workflow Discipline

- **One target per run.** Never extend scope implicitly to "and also the day before".
- **Never edit raw files.** The wrap-up reads `data/raw/ops/cron/{Y}/{M}/{TARGET}_*.log` as evidence and `git add`s them on commit, but must never modify their contents. Do not read other `data/raw/` subtrees.
- **Replay caveat.** A wrapper rerunning for an already-written TARGET will append to a tracked raw log. If you must replay a job for a committed TARGET, use the DB API to manage the existing log entry before the wrapper runs.
- **Do not auto-promote** anything — wiki promotion is `wiki-approval`'s job.
- **Do not use lint as analysis input** — run only the required final gate: `kb-lint all` once.
- **Persist only through the DB API.** Never commit outer repo files or generated `data/` export.
- **If blocked**, write the handoff with `status: ready` and the wrap-up with `Status: FAILED`, then exit non-zero.

## Red Flags — STOP and re-check

- About to read any cron log other than `raw/ops/cron/{Y}/{M}/{TARGET}_*.log` → STOP. The wrap-up summarizes exactly this target's per-run files; no time-window scan. (`{TARGET}_kb-cron-wrapup.log` does not exist during the session — the shell wrapper creates and commits it after the session exits; never read or stage it.)
- About to inspect `git status` or prepare a data commit → STOP. DB rows are the source of truth.
- About to re-render the full memory page into the wrap-up → STOP. Extract only concise insights and action items.
- About to rename or reorder one of the seven H2 sections → STOP. The Slack digest will break.
- About to create a wiki page by editing `data/wiki` directly → STOP. Submit `POST /api/pages`.
- About to put `data/wiki/...` in `sources:` → drop the `data/` prefix
- About to mark Status: OK while Anomalies list is non-empty → re-read the Status table; non-empty anomaly = DEGRADED at minimum
- About to overwrite a prior cron-wrapup handoff with the same NN → bump NN, never overwrite handoffs
- About to invoke this skill twice in one cron firing → STOP. One run, one wrap-up, one handoff.
- About to run any `git commit` for generated KB data → STOP. Use the DB API.
