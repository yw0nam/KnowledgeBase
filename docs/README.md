# Documentation Index

Updated: 2026-05-28

## 1. Synopsis

- **Purpose**: Route humans and agents to project skills for workflows and compact docs for reference.
- **I/O**: Question or task type -> skill for execution or document for design context.

## 2. Core Logic

### Runtime Skills First

Agents should execute core workflows from `.claude/skills/`, not by loading workflow docs:

| Task | Runtime contract |
|---|---|
| Initialize a clone/profile | `.claude/skills/knowledgebase-initialize/SKILL.md` |
| Write or fix wiki pages (evidence-derived) | `.claude/skills/wiki-authoring/SKILL.md` |
| Capture a first-party note (human, no source) | `.claude/skills/wiki-note/SKILL.md` |
| Promote/approve/reject wiki pages | `.claude/skills/wiki-approval/SKILL.md` |
| Configure usage reports | `.claude/skills/usage-report-setup/SKILL.md` |
| Daily/weekly/monthly memory build | `.claude/skills/memory-report/SKILL.md` |
| Write handoff documents | `.claude/skills/handoff-document/SKILL.md` |

For human onboarding, read:

1. `CLAUDE.md`
2. `docs/architecture.md`
3. The relevant skill or reference document if needed

### Directory Map

| Path | Role |
|---|---|
| `docs/architecture.md` | System layout and data boundaries |
| `docs/reference/` | Human-readable schemas, categories, commands, and lookup tables |
| `docs/db_informations/` | Database and reporting references |
| `docs/workflows.md` | At-a-glance diagram map: nightly pipeline, review lifecycle, data sync (overview only — skills own execution) |
| `docs/data-sync.md` | Private remote sync for the nested `data/` repo |
| `docs/CLAUDE.md` | Document authoring rules |

### Document Types

Use project skills for ordered execution steps. Use `docs/reference/` for human-readable lookup material. Keep root `docs/` limited to index, architecture, and authoring guidance.

## 3. Usage

| Need | Read |
|---|---|
| Understand the repo | `docs/architecture.md` |
| See the whole picture at a glance | `docs/workflows.md` |
| Run raw-to-wiki pipeline | `.claude/skills/wiki-authoring/SKILL.md` |
| Jot a first-party note (no source, from any repo) | `.claude/skills/wiki-note/SKILL.md` |
| Configure cron jobs | `.claude/skills/knowledgebase-initialize/SKILL.md` |
| Configure usage reports | `.claude/skills/usage-report-setup/SKILL.md` |
| Run daily/weekly/monthly memory build | `.claude/skills/memory-report/SKILL.md` |
| Handle handoff lifecycle | `.claude/skills/handoff-document/SKILL.md` |
| Write valid frontmatter | `.claude/skills/wiki-authoring/SKILL.md`; reference: `docs/reference/frontmatter.md` |
| Choose wiki category/path | `.claude/skills/wiki-authoring/SKILL.md`; reference: `docs/reference/wiki-categories.md` |
| Approve/reject wiki pages | `.claude/skills/wiki-approval/SKILL.md` |
| Run CLI commands | `docs/reference/commands.md` |
| Start review console (web UI) | `README.md` → "Review console" section; `scripts/dev-web.sh` |
| Sync `data/` across machines | `docs/data-sync.md`; `.claude/skills/data-sync/SKILL.md` |

---

## Appendix

### A. PatchNote

- 2026-06-02: Added the `wiki-note` skill (first-party human-authored pages, `origin: authored`) to runtime routing + usage tables; it is exposed globally like `handoff-document`.
- 2026-06-02: Added `docs/workflows.md` — at-a-glance Mermaid map of the nightly pipeline, review lifecycle, and two-repo sync.
- 2026-05-29: Updated data-sync sync entry to point at the `data-sync` skill.
- 2026-05-28: Added `docs/data-sync.md` for private remote sync of the nested `data/` repo.
- 2026-05-20: Removed `docs/workflows/`; project skills are now the sole workflow surface.
- 2026-05-20: Reframed docs as design/reference material and routed runtime workflows to `.claude/skills/`.
- 2026-05-20: Added review console (web UI) to usage table.
- 2026-05-19: Added wiki approval workflow to runtime routing and usage table.
- 2026-05-18: Added cron job workflow to memory build routing.
- 2026-05-18: Added usage report workflow for source-specific OpenCode/Hermes reports.
- 2026-05-18: Initial documentation index after workflow/reference split.
