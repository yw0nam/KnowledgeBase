# Architecture

Updated: 2026-06-04

## 1. Synopsis

- **Purpose**: Explain the KnowledgeBase repository layout, data boundaries, and memory layers.
- **I/O**: Repository path or data file -> correct layer, owner, and mutation rule.

## 2. Core Logic

### Repository Boundary

KnowledgeBase has one git repository and one generated data directory:

| Repo | Path | Purpose | Push Policy |
|---|---|---|---|
| Outer repo | `KnowledgeBase/` | Code, docs, templates, lint tools | Public-safe |
| Generated export | `data/` | Raw sources, wiki, handoffs, logs (Postgres via `DATABASE_URL` is SoT; `data/` is generated export) | Local-only |

Never commit `data/` contents to the outer repository. The outer `.gitignore` excludes `data/`.

### Memory Layers

| Layer | Path | Meaning | Mutation Rule |
|---|---|---|---|
| Raw | `data/raw/` | Captured source evidence | Create only; never edit existing files |
| Handoffs | `data/handoffs/` | Operational state and agent handoff | Update during tasks and periodic runs |
| Wiki | `data/wiki/` | Durable long-term knowledge | Update only with source-backed frontmatter |
| Rejected | `data/rejected/` | Wiki pages rejected during review (audit trail) | Populated through DB API reject endpoint; mirrors `wiki/` tree |
| Log | `data/log.md` | Append-only operation history | Append every operation |
| Skill templates | `.claude/skills/*/reference/templates` | Runtime file skeletons bundled with skills | Update in outer repo |
| Raw templates | `docs/raw/` | Raw source frontmatter skeletons | Update in outer repo |
| Docs | `docs/` | Design references and human-readable lookup material | Update in outer repo |

### Wiki Shape

`data/wiki/` is organized by knowledge type:

```text
data/wiki/
  entities/       # named objects by subject/month
  concepts/       # reusable abstract ideas
  decisions/      # closed architecture or workflow decisions
  questions/      # preserved Q&A
  improvements/   # open-ended improvements
  checklists/     # repeatable operating procedures
  summaries/      # daily, weekly, monthly, migration rollups
```

Six of the seven types (`entity`, `concept`, `decision`, `improvement`, `checklist`, `question`) carry a `review_status` field (`not_processed` → `pending_for_approve` → `approved`) managed through DB API (promote/approve/reject endpoints). Summaries are exempt. Only `approved` pages appear in `INDEX.md`. Runtime approval work uses `.claude/skills/wiki-approval/SKILL.md`.

### Operating Flow

The DB-canonical flow is:

```text
data/raw/ -> kb-mcp tools / service layer -> Postgres write -> data/wiki/ (Markdown export) -> data/log.md -> lint
```

Writes go through the `kb-mcp` MCP server tools or the in-process `kb.service` layer (used by cron CLIs); Markdown files under `data/wiki/` are generated exports
exported from Postgres. Handoffs sit beside the flow as the operational state
board. They record what was processed, what is blocked, and what the next agent should do.

Postgres (reached via `DATABASE_URL`) is the canonical memory store — it owns pages,
frontmatter, raw sources, citations, and revisions. Markdown under `data/` is generated
from the DB. See `docs/db-canonical.md`.

### DB-Canonical MCP Server + Service Layer

A local-only FastMCP server (streamable-http, `127.0.0.1:8765`, no auth) that exposes
write operations as MCP tools. All writes follow the same invariant: lint → DB write → Markdown export.
Reads go directly to Postgres via the `query_sql` MCP tool or `psql`; Markdown under `data/wiki/`
is a generated export, not a read surface.

| Component | Path | Role |
|---|---|---|
| `kb-mcp` FastMCP server | `src/kb/mcp/` | 12 write tools + `query_sql`/`get_schema` read tools over Postgres |
| Service layer | `src/kb/service/` | In-process write path (lint → DB → export); called by cron CLIs without a running server |

## 3. Usage

When deciding where information belongs:

| Information | Put It In |
|---|---|
| External source capture | `data/raw/` |
| Current task state or next action | `data/handoffs/` |
| Durable concept or entity | `data/wiki/` |
| Execution record | `data/log.md` |
| Reusable runtime skeleton | `.claude/skills/<skill>/reference/templates` |
| Agent operating instruction | `.claude/skills/` |
| Human schema or command reference | `docs/reference/` |

---

## Appendix

### A. PatchNote

- 2026-06-12: Replaced the FastAPI write API (`kb-web`) with the `kb-mcp` FastMCP server (`src/kb/mcp/`, streamable-http, 127.0.0.1:8765, no auth) plus an in-process `src/kb/service/` layer. Reads via `query_sql`/`get_schema` MCP tools or `psql`. Updated data-flow, components table, and PatchNotes accordingly.
- 2026-06-04: Postgres is now the sole source of truth; SQLite (`state.db`) removed. Reads go directly to Postgres via `psql`; writes went through the FastAPI API (replaced 2026-06-12 by `kb-mcp`). `data/` is a generated Markdown export, not canonical.
- 2026-06-04: Added DB-canonical target direction; Markdown/Git flow is now documented as legacy/current rather than the end state.
- 2026-05-20: Removed workflow docs from the active documentation map; project skills are the runtime workflow layer.
- 2026-05-20: Reframed workflow docs as design references and `.claude/skills/` as runtime operating instructions.
- 2026-05-20: Added Web Review Console section (FastAPI + React SPA, `src/kb/web/`, `frontend/`, `scripts/dev-web.sh`) — replaced 2026-06-12.
- 2026-05-19: Added `data/rejected/` memory layer; noted `review_status` on six in-scope wiki types.
- 2026-05-18: Initial architecture overview after docs restructuring.
