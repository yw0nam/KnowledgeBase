# Commands

Updated: 2026-05-18

## 1. Synopsis

- **Purpose**: KnowledgeBase CLI commands for validating wiki/handoff content and generating reports.
- **I/O**: Shell command → lint report (exit 0 = pass, non-zero = fail).
- **Runtime**: Workflow ordering lives in `.claude/skills/`; this document is command reference.

## 2. Core Logic

### kb-lint-wiki

Validate wiki pages.

```bash
kb-lint-wiki                      # errors only
kb-lint-wiki --strict             # errors + warnings (auto-enables --check-immutability)
kb-lint-wiki --check-immutability # enforce raw file immutability
```

### kb-lint-handoff

Validate handoff documents.

```bash
kb-lint-handoff
```

### kb-wiki-index

Regenerate `data/wiki/INDEX.md`, the auto-built table of contents grouping all
wiki pages by category. Idempotent — running on an unchanged wiki rewrites
nothing. `kb-lint-wiki` will ERROR if INDEX.md is stale. Only `approved`
pages appear in `INDEX.md`.

```bash
kb-wiki-index
```

### kb-wiki-review

Manage wiki page approval lifecycle. Applies to 6 in-scope types only
(`entity`, `concept`, `decision`, `improvement`, `checklist`, `question`).

```bash
kb-wiki-review list [--status STATUS] [--counts]   # default --status pending_for_approve
kb-wiki-review promote <stem>                       # not_processed → pending_for_approve
kb-wiki-review approve <stem> [--feedback "..."]   # pending_for_approve → approved
kb-wiki-review reject  <stem> [--feedback "..."]   # pending_for_approve → rejected (git mv to data/rejected/)
kb-wiki-review ttl-sweep [--days 7]                 # cron only — auto-reject stale not_processed
```

`<stem>` is the filename without `.md`. STATUS ∈ `not_processed | pending_for_approve | approved | all`.
Empty `--feedback` (or empty interactive input) skips the `## User Feedback` line append.

Use `.claude/skills/wiki-approval/SKILL.md` for the full lifecycle.

### kb-web

Start the local FastAPI review console server.

```bash
./scripts/dev-web.sh        # API :8765 + Vite :5173 — use this during development
kb-web --reload --port 8765 # API only, with auto-reload
```

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `KB_DATA_DIR` | `<repo>/data` | Path to the local data tree |
| `KB_WEB_PORT` | `8765` | FastAPI port |
| `VITE_PORT` | `5173` | Vite dev server port |

API endpoints: `GET /api/queue`, `GET /api/pages/{stem}`, `GET /api/dashboard?window={4,8,12,24}`, `POST /api/pages/{stem}/approve`, `POST /api/pages/{stem}/reject`. Swagger UI at `/api/docs`.

## 3. Usage

Use this file to look up command names and flags. Use `.claude/skills/` for command ordering:

| Task | Skill |
|---|---|
| Write wiki pages | `.claude/skills/wiki-authoring/SKILL.md` |
| Review/promote pages | `.claude/skills/wiki-approval/SKILL.md` |
| Write handoffs | `.claude/skills/handoff-document/SKILL.md` |
| Run periodic memory | `.claude/skills/memory-report/SKILL.md` |

---

## Appendix

### A. Troubleshooting

**kb-lint-wiki errors on dead wikilink**
Fix the link or use plain text instead of a wikilink.

**kb-lint-wiki --check-immutability fails**
A raw file was modified. Revert the raw file to its original state.

**kb-lint-handoff fails on missing frontmatter field**
Add the missing field to the handoff document frontmatter.

### B. PatchNote

- 2026-05-20: Added `kb-web` command and `dev-web.sh` for the local FastAPI + Vite review console.
- 2026-05-20: Routed workflow ordering to project skills; this doc remains command reference.
- 2026-05-20: Removed links to deleted workflow docs.
- 2026-05-19: Added `kb-wiki-review` CLI (5 subcommands) for `review_status` lifecycle.
- 2026-05-18: Added kb-wiki-index — generates `data/wiki/INDEX.md`. Enforced by `kb-lint-wiki`.
- 2026-05-18: Removed kb-mcp (MCP server retired in favor of direct CLI usage by Claude Code agents).
- 2026-05-18: Added pointer to periodic memory workflow for cron agents.
- 2026-05-08: Initial split from CLAUDE.md and restructured to follow docs/CLAUDE.md Standard Document Structure.
