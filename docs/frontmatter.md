# Frontmatter Conventions

Updated: 2026-05-08

## 1. Synopsis

- **Purpose**: Define YAML frontmatter schemas for raw sources, wiki pages, and handoff documents.
- **I/O**: Markdown file → validated frontmatter block at the top of the file.

## 2. Core Logic

### Raw files

```yaml
---
source_url: "https://..."
type: github_issue | claude_md | conversation | calendar_event | web_article | manual
captured_at: "2026-04-15T09:00:00Z"
author: "who wrote it"
contributor: "who added it"
tags: []
---
```

Use this schema when capturing external sources into `data/raw/`.

### Wiki pages

Always use YAML block style for lists. Never quote scalar values except dates.

```yaml
---
type: entity | concept | decision | question | improvement | checklist | summary
created: "2026-04-15"
updated: "2026-04-15"
sources:
  - raw/github/issues/repo_42.md
aliases: []
tags: []
---
```

Note: `sources:` paths are relative to `data/` (the parent of `data/wiki/`). Use `raw/...`, not `data/raw/...`.

### Handoff documents

```yaml
---
handoff_id: <task-slug>:<subject>:<role>:01
task_slug: <task-slug>
subject: <subject-or-null>
role: main_gateway | research | structuring | execution | verification
handoff_seq: 1
status: draft | ready | consumed | superseded
security:
  contains_secrets: false
  redaction_status: unchecked
promotion: null | skill_candidate | memory | wiki_entity | wiki_concept
---
```

Use this schema when drafting task handoff documents in `data/raw/handoffs/`.

## 3. Usage

**Adding a GitHub issue raw file:**

```yaml
---
source_url: "https://github.com/owner/repo/issues/42"
type: github_issue
captured_at: "2026-05-08T14:30:00Z"
author: "alice"
contributor: "bob"
tags: [bug, urgent]
---
```

**Creating a wiki entity page from one raw file:**

```yaml
---
type: entity
created: "2026-05-08"
updated: "2026-05-08"
sources:
  - raw/github/issues/repo_42.md
aliases: [Issue #42]
tags: [bug]
---
```

**Drafting a handoff document:**

```yaml
---
handoff_id: migrate-db:schema:execution:01
task_slug: migrate-db
subject: schema
role: execution
handoff_seq: 1
status: draft
security:
  contains_secrets: false
  redaction_status: unchecked
promotion: null
---
```

---

## Appendix

### A. Troubleshooting

**Wrong sources path prefix:**
- Wrong: `sources: - data/raw/github/issues/repo_42.md`
- Right: `sources: - raw/github/issues/repo_42.md`

**Quoted scalars when not needed:**
- Wrong: `author: "alice"` (for non-date fields)
- Right: `author: alice`

**Missing required fields:**
- Raw files must have: `source_url`, `type`, `captured_at`, `contributor`
- Wiki pages must have: `type`, `created`, `updated`, `sources`
- Handoff documents must have: `handoff_id`, `task_slug`, `role`, `status`

**Flow style instead of block style for lists:**
- Wrong: `sources: [raw/github/issues/repo_42.md]`
- Right: `sources:\n  - raw/github/issues/repo_42.md`

### B. PatchNote

- 2026-05-08: Initial split from CLAUDE.md and restructured to follow docs/CLAUDE.md Standard Document Structure.
