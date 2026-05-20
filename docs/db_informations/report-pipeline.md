# Report Pipeline — Source-Specific Daily Reports

Updated: 2026-05-18

## 1. Synopsis

- **Purpose**: Define the source-specific daily report pipeline for OpenCode, Hermes, and Claude Code.
- **Format**: All reports are Markdown. Storage root: `data/wiki/summaries/`.

---

## 2. Pipeline Structure

```
OpenCode DB      -> data/wiki/summaries/YYYY/MM/YYYY-MM-DD-opencode-usage.md
Hermes DB        -> data/wiki/summaries/YYYY/MM/YYYY-MM-DD-hermes-usage.md
Claude telemetry -> data/wiki/summaries/YYYY/MM/YYYY-MM-DD-claude-code-usage.md

Daily memory cron reads source-specific reports and writes:
data/wiki/summaries/YYYY/MM/YYYY-MM-DD-memory.md
```

### Source Responsibilities

| Source | Metrics | Reason |
|------|----------|------|
| `message.data` (modelID, tokens, cost) | Model tokens, recorded cost, shadow cost inputs | Records actual model names across root and subagent sessions. |
| `session` (parent_id, time_created) | Session count, root/subagent split, hourly distribution, project distribution | Session structure source. |
| `part` (type=tool, patch, compaction) | Tool error rate, hot files, compaction | In-session behavior data. |
| `todo` | TODO completion rate | Work quality proxy. |
| SQLite `hermes/state.db` | Hermes metrics | Source of truth for Hermes source-specific reports. |

---

## 3. Common Rules

### Date Boundary
- Default boundary: one local day in KST (UTC+9) unless configured otherwise.
- Session attribution: `session.time_created` or source-equivalent session start time.
- Query range: local day start <= session start < next local day start.
- OpenCode: `time_created` is Unix epoch milliseconds.
- Hermes: `started_at` is Unix epoch seconds.

### Missing Source Handling
- If a selected source DB/telemetry is missing, skip only that source report.
- Continue generating other selected source reports.
- Record the skip reason in the wrapper log or handoff.

### Filename Rules
- OpenCode: `YYYY-MM-DD-opencode-usage.md`
- Hermes: `YYYY-MM-DD-hermes-usage.md`
- Claude Code: `YYYY-MM-DD-claude-code-usage.md`
- Daily memory synthesis: `YYYY-MM-DD-memory.md`
- Weekly synthesis: `YYYY-WNN-weekly.md`
- Monthly synthesis: `YYYY-MM-monthly.md`

### Weekly Synthesis Method
- Do not re-query DBs.
- Read source-specific daily reports and daily memory summaries.
- Mark missing sources as `not configured` or `missing`.

---

## 4. Templates

- Source-specific daily reports are rendered by CLI commands.
- Memory synthesis summaries follow `.claude/skills/memory-report/SKILL.md`.

**Empty-day handling**: If a configured source has no activity, write `no activity`. If the source itself is missing, do not create that report.

## 5. Cost Calculation

### Cost Source

- **Recorded cost**: `SUM(message.data.cost)`. OpenCode records this across models.

### providerID Handling

| providerID | Cost Source |
|------------|----------|
| `anthropic` | `message.data.cost` (OpenCode recorded cost) |
| `openai` | `message.data.cost` (OpenCode recorded cost) |
| `google` | `message.data.cost` (OpenCode recorded cost) |
| `opencode-go` | `message.data.cost` (actual recorded cost) |
| `vllm` | 0 USD (self-hosted, excluded from cost aggregation) |

---

## Appendix

### A. Full Storage Layout

```
data/wiki/summaries/
└── 2026/
    └── 05/
        ├── 2026-05-10-opencode-usage.md
        ├── 2026-05-10-hermes-usage.md
        ├── 2026-05-10-claude-code-usage.md
        ├── 2026-05-10-memory.md
        ├── 2026-W19-weekly.md
        └── 2026-05-monthly.md
```

### B. Signal-To-Action References

Use these thresholds when interpreting daily/weekly signals:
- `opencode-monitoring-guide.md` §4
- `hermes-monitoring-guide.md` §3
