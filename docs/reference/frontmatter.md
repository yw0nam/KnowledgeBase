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
| Wiki pages | `.claude/skills/wiki-authoring/SKILL.md` |
| Wiki review fields | `.claude/skills/wiki-approval/SKILL.md` |
| Handoff documents | `.claude/skills/handoff-document/SKILL.md` |
| Usage report summaries | `.claude/skills/usage-report-setup/SKILL.md` |

Universal wiki source rule:

```text
sources: paths are relative to data/
right: raw/github/issues/repo_42.md
wrong: data/raw/github/issues/repo_42.md
```

## Appendix

### PatchNote

- 2026-05-20: Reduced to human lookup; runtime schemas moved to skills.
