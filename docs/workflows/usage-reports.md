# Usage Reports

Updated: 2026-05-18

## 1. Synopsis

- **Purpose**: Define how KnowledgeBase should generate source-specific agent usage reports.
- **I/O**: agent usage databases or telemetry -> daily markdown reports under `data/wiki/summaries/YYYY/MM/` + metrics JSON under `data/ops/reports/YYYY/MM/`.

## 2. Core Logic

### Default Policy

Generate separate reports by default:

```text
OpenCode source    -> YYYY-MM-DD-opencode-usage.md
Hermes source      -> YYYY-MM-DD-hermes-usage.md
Claude Code source -> YYYY-MM-DD-claude-code-usage.md
```

Reason: not every user has every agent system. Source-specific reports avoid making missing systems look like failures. Daily memory workflows can later read multiple source-specific reports and synthesize a separate memory summary.

### Modes

| Mode | Required Source | Output | Cron Default |
|---|---|---|---|
| OpenCode only | OpenCode DB | `YYYY-MM-DD-opencode-usage.md` | optional |
| Hermes only | Hermes DB | `YYYY-MM-DD-hermes-usage.md` | optional |
| Claude Code only | Claude Code telemetry | `YYYY-MM-DD-claude-code-usage.md` | optional |
| Multiple separate reports | 2+ source systems | one markdown per source | recommended when multiple exist |
| Disabled | none | none | valid |

### Missing Source Handling

If a selected source is missing:

1. Do not fail unrelated report jobs.
2. Write a skipped handoff or wrapper log entry.
3. Do not generate a misleading empty success report unless the user explicitly wants empty-day reports.

### Output Rules

All usage reports must:

- use `type: summary`
- use `subtype: daily`
- use `sources: []` when the source is a local DB rather than a `data/raw/` file
- avoid dollar signs; write `N USD`
- write metrics JSON to `data/ops/reports/YYYY/MM/`
- run `uv run kb-lint-wiki` after writing markdown

### Command Naming

Preferred command names:

```text
kb-opencode-daily-report
kb-hermes-daily-report
kb-claude-code-daily-report
```

Do not generate a combined usage report in this layer. The daily memory workflow is the only combined interpretation layer; it reads source-specific reports and writes `YYYY-MM-DD-memory.md`.

## 3. Usage

During initialization, ask which modes to enable:

```text
Which usage reports should this KnowledgeBase generate?
- none
- OpenCode only
- Hermes only
- Claude Code only
- multiple source-specific reports
```

Recommended cron ordering:

```text
03:10 OpenCode daily usage report
03:15 Hermes daily usage report
03:20 Claude Code daily usage report
03:30 KnowledgeBase daily memory build
```

The daily memory build should run after usage reports so it can ingest or summarize generated report pages if needed.

---

## Appendix

### A. Template Policy

Daily source-specific usage reports are rendered deterministically by CLI commands and do not need markdown templates. Weekly and monthly synthesis reports are LLM-written and should use templates such as `templates/wiki/summaries/weekly.md`.

### B. Migration Note

The old combined report command is removed from the portable setup. If a combined view is needed, implement it as a memory synthesis step that reads source-specific reports.

### C. PatchNote

- 2026-05-18: Clarified deterministic daily reports do not need templates; weekly synthesis does.
- 2026-05-18: Initial usage report mode policy with OpenCode/Hermes split by default.
