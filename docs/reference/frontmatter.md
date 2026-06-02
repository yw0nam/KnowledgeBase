# Frontmatter Reference

Updated: 2026-05-20

## 1. Synopsis

- **Purpose**: Human lookup for the major frontmatter families.
- **Runtime**: Use `.claude/skills/wiki-authoring/SKILL.md` for wiki pages and `.claude/skills/handoff-document/SKILL.md` for handoffs.

## 2. Raw Files

Raw source files are immutable after creation.

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

Use `docs/raw/` for raw frontmatter skeletons.

## 3. Runtime Schemas

Detailed runtime schemas live in skills:

| File kind | Runtime contract |
|---|---|
| Wiki pages (evidence-derived) | `.claude/skills/wiki-authoring/SKILL.md` |
| Wiki pages (first-party, human-authored) | `.claude/skills/wiki-note/SKILL.md` |
| Wiki review fields | `.claude/skills/wiki-approval/SKILL.md` |
| Handoff documents | `.claude/skills/handoff-document/SKILL.md` |
| Usage report summaries | `.claude/skills/usage-report-setup/SKILL.md` |

Universal wiki source rule:

```text
sources: paths are relative to data/
right: raw/github/issues/repo_42.md
wrong: data/raw/github/issues/repo_42.md
```

Provenance — `origin` (optional, default `ingested`):

```text
origin: ingested   default; page derived from a data/raw source → cite it in sources: (wiki-authoring convention)
origin: authored   first-party human note; no external source → sources: [] is fine
```

`origin` is optional and lint does not require it; absence means `ingested`. Lint
already accepts `sources: []` for any page — the citation expectation for `ingested`
pages is a convention enforced by `wiki-authoring`, not the linter. Only human
authoring via `wiki-note` should set `authored`; LLM/cron pages stay `ingested` and
must cite real sources.

## Appendix

### PatchNote

- 2026-06-02: Documented the `origin` field (`ingested` default vs `authored` first-party) and the `wiki-note` skill for human-authored source-less pages.
- 2026-05-20: Reduced to human lookup; runtime schemas moved to skills.
