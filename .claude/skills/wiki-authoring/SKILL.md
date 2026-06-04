---
name: wiki-authoring
description: Use when creating or updating source-backed DB wiki pages — selecting entity/concept/decision/question/improvement/checklist/summary types, applying frontmatter schemas, validating wikilinks, and submitting writes through the DB API.
---

# Wiki Authoring

Use this skill as the runtime contract for raw-to-wiki authoring. DB rows are the
source of truth; Markdown under `data/` is generated export. Do not look for a
workflow doc during execution; this skill is the complete operating surface.

> **Evidence-derived only.** This skill is for pages grounded in a `data/raw` source — including all LLM/cron authoring, which MUST cite real sources. For a **first-party human note** with no external source, use the `wiki-note` skill (`origin: authored`, `sources: []`); do not fake a citation here.

## Rules

- Never modify existing exported files under `data/raw/`.
- Every wiki page must cite `sources:` paths relative to `data/`, for example `raw/github/issues/repo_42.md`.
- Never use `data/raw/...` or absolute paths in `sources:`.
- Use wikilinks only to existing file stems. `aliases:` do not satisfy lint.
- Do not use the reserved `## User Feedback` heading in authored content.
- New `entity`, `concept`, `decision`, `improvement`, `checklist`, and `question` pages start with `review_status: not_processed`.
- If semantically editing an `approved` page, reset `review_status: not_processed`; keep `approved` only for typo/format-only edits.

## Bundled Templates

Copy from `reference/templates/`:

```text
entity.md
concept.md
decision.md
question.md
improvement.md
checklist.md
summaries/weekly.md
summaries/monthly.md
```

Daily summaries do not need a separate template; use the summary schema below.

## Pipeline

```text
1. Select source evidence
2. Choose wiki type and path
3. Copy or follow the matching template
4. Fill frontmatter and body from sources only
5. Submit `POST /api/pages` or `PATCH /api/pages/{slug}` with Bearer auth
6. Submit `POST /api/operation-logs` for the operation note
7. Confirm the API response reports `export.status: success`
```

## Type And Path

| Type | Path | Use for |
|---|---|---|
| `entity` | `data/wiki/entities/<subject>/YYYY-MM/<stem>.md` | named project, repo, PR, issue, person, tool, event |
| `concept` | `data/wiki/concepts/<stem>.md` | reusable idea, pattern, protocol |
| `decision` | `data/wiki/decisions/YYYY-MM-DD-<slug>.md` | closed choice with rationale |
| `question` | `data/wiki/questions/<stem>.md` | reusable Q&A |
| `improvement` | `data/wiki/improvements/YYYY-MM/<stem>.md` | open issue, proposal, improvement |
| `checklist` | `data/wiki/checklists/<stem>.md` | repeatable procedure |
| `summary` | export path `wiki/summaries/YYYY/MM/<period>-<kind>.md` | daily/weekly/monthly rollup |

Use stable ASCII slugs unless an existing local convention requires otherwise.

## Frontmatter Schemas

### entity / concept / question

```yaml
---
type: entity
review_status: not_processed
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources:
  - raw/...
aliases: []
tags: []
---
```

Use `type: concept` or `type: question` as appropriate. `aliases:` is required for entity and concept templates; keep it harmless on question pages if the copied template includes it.

### decision

```yaml
---
type: decision
review_status: not_processed
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources:
  - raw/...
tags: [decision]
---
```

Filename must carry the decision date: `YYYY-MM-DD-<slug>.md`.

### improvement

```yaml
---
type: improvement
review_status: not_processed
kind: improvement
observed_at: "YYYY-MM-DD"
domain: dx
severity: med
issue_status: open
related: []
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources:
  - raw/...
tags: []
---
```

Enums:

- `kind`: `improvement | issue | proposal`
- `domain`: `cost | correctness | perf | dx | security`
- `severity`: `low | med | high`
- `issue_status`: `open | acknowledged | resolved | wontfix`

### checklist

```yaml
---
type: checklist
review_status: not_processed
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources:
  - raw/...
tags: []
---
```

Body must include `## Items` with task-list syntax:

```markdown
## Items

- [ ] First repeatable action
```

### summary

```yaml
---
type: summary
subtype: daily
date: "YYYY-MM-DD"
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources:
  - raw/...
tags: []
---
```

Weekly/monthly summaries use `period_start` and `period_end`; weekly also has `week: "YYYY-WNN"`. Summaries do not use `review_status`.

## Promotion Criteria

Create an atomic wiki page only when the content has durable future value. Otherwise keep it in the period summary or handoff.

| Target | Promote when |
|---|---|
| entity | named thing will need future lookup |
| concept | pattern repeats or explains reusable behavior |
| decision | choice is closed and rationale is captured |
| question | Q&A is complete and likely to recur |
| improvement | unresolved actionable work exists |
| checklist | procedure should be repeated |

## DB Write Contract

Use the local API unless the environment specifies another base URL:

```bash
KB_API_URL="${KB_API_URL:-http://127.0.0.1:8765}"
curl -fsS -X POST "$KB_API_URL/api/pages" \
  -H "Authorization: Bearer $KB_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data @page.json
```

`page.json` must include `slug`, `type`, `frontmatter`, `body_md`, and
`export_path`. The API appends a revision and exports Markdown immediately.
Do not manually regenerate `INDEX.md`; it is generated export from the DB.

Common fixes:

| Error | Fix |
|---|---|
| `INDEX.md: stale` | DB export owns generated files; INDEX.md is regenerated on DB write |
| source not found | remove `data/` prefix; verify path exists under `data/` |
| dead wikilink | link to exact file stem or use plain text |
| improvement missing fields | fill all six improvement-specific fields |
| checklist missing items | add `## Items` with `- [ ]` tasks |
| raw immutability violation | do not edit raw; report the external blocker |

## Log Format

Submit to `POST /api/operation-logs`:

```markdown

## YYYY-MM-DD (wiki authoring)

- **sources**: raw/...
- **created/updated**: wiki/...
- **review_status**: not_processed
- **db_write**: page export succeeded
```

## Red Flags

- About to author from memory without a cited source path.
- About to create a wikilink to a page that does not exist.
- About to write an improvement without `kind`, `observed_at`, `domain`, `severity`, `issue_status`, and `related`.
- About to lint before DB write — DB API validates on submission; INDEX.md is regenerated automatically.
