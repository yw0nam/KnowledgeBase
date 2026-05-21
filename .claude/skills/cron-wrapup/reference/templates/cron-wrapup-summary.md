---
type: summary
subtype: cron-daily
date: "YYYY-MM-DD"
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources:
  - wiki/summaries/YYYY/MM/YYYY-MM-DD-memory.md
  - wiki/summaries/YYYY/MM/YYYY-MM-DD-opencode-usage.md
  - wiki/summaries/YYYY/MM/YYYY-MM-DD-claude-code-usage.md
  - wiki/summaries/YYYY/MM/YYYY-MM-DD-hermes-usage.md
  - handoffs/YYYY/MM/wiki-daily-build/YYYY-MM-DD_role_handoff_NN.md
tags: [cron-wrapup, ops-daily]
---

# Cron Wrap-up — YYYY-MM-DD

## Status

OK

(Replace with OK | DEGRADED | FAILED on the first line. Optional one-sentence elaboration on the second line.)

## Jobs

| Job | Schedule | Exit | Output | Notes |
| --- | --- | --- | --- | --- |
| kb-wiki-ttl-sweep           | 30 0 * * *  | 0 | (log only)                                            | 0 pages expired |
| kb-opencode-daily-report    | 10 3 * * *  | 0 | wiki/summaries/YYYY/MM/YYYY-MM-DD-opencode-usage.md   | N sessions, X.XX USD |
| kb-hermes-daily-report      | 15 3 * * *  | 0 | wiki/summaries/YYYY/MM/YYYY-MM-DD-hermes-usage.md     | N sessions, zombie N |
| kb-claude-code-daily-report | 20 3 * * *  | 0 | wiki/summaries/YYYY/MM/YYYY-MM-DD-claude-code-usage.md| N sessions, X.XX USD |
| kb-memory-daily             | 30 3 * * *  | 0 | wiki/summaries/YYYY/MM/YYYY-MM-DD-memory.md           | N new pages |
| kb-wiki-promote             | 0 4 * * *   | 0 | handoffs/YYYY/MM/wiki-promote/...                     | N promoted |

(Omit a row if a job did not run that day, e.g. weekly/monthly on non-eligible days. Do not invent rows.)

## Insights

- none

(Replace with 1-5 user-facing signals from the daily memory page, usage reports, and run handoffs: new improvement pages, recurring error trends, cost spikes, completed work that needs review, newly blocked work, or promotion candidates. Use `- none` only when no meaningful new signal exists.)

## Action Items

| Priority | Owner | Item | Source |
| --- | --- | --- | --- |
| none | none | none | none |

(Replace with concrete follow-ups from daily memory Open Items / Next Run Notes, run handoff Next handoff instructions, and unresolved improvement pages. Owner should be `user`, `agent`, or `unknown`.)

## Anomalies

- none

(Replace with bullet list of anomalies — non-zero exits, missing inputs, lint failures, lock skips, late starts > 10 min. Use the literal line `- none` when empty.)

## Counters

| Metric | Value |
| --- | --- |
| pages_created       | 0 |
| pages_promoted      | 0 |
| pages_ttl_swept     | 0 |
| insights_count      | 0 |
| action_items_count  | 0 |
| lint_errors         | 0 |
| lint_warnings       | 0 |
| total_usd           | 0.00 |
| sessions_total      | 0 |

(Add new snake_case keys only if a follow-up Slack digest needs them.)

## Links

- memory:          wiki/summaries/YYYY/MM/YYYY-MM-DD-memory.md
- opencode:        wiki/summaries/YYYY/MM/YYYY-MM-DD-opencode-usage.md
- claude:          wiki/summaries/YYYY/MM/YYYY-MM-DD-claude-code-usage.md
- hermes:          wiki/summaries/YYYY/MM/YYYY-MM-DD-hermes-usage.md
- daily-handoff:   handoffs/YYYY/MM/wiki-daily-build/YYYY-MM-DD_role_handoff_NN.md
- promote-handoff: handoffs/YYYY/MM/wiki-promote/...

(Omit a line if the artefact was not produced that day.)
