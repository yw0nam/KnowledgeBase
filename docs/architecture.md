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
data/raw/ -> FastAPI API -> Postgres write -> data/wiki/ (Markdown export) -> data/log.md -> lint
```

Writes go through the DB API; Markdown files under `data/wiki/` are generated exports
exported from Postgres. Handoffs sit beside the flow as the operational state
board. They record what was processed, what is blocked, and what the next agent should do.

Postgres (reached via `DATABASE_URL`) is the canonical memory store — it owns pages,
frontmatter, raw sources, citations, and revisions. Markdown under `data/` is generated
from the DB. See `docs/db-canonical.md`.

### DB-Canonical API Server

A local-only FastAPI server that serves wiki pages and review operations from
Postgres via Bearer-auth REST API. Markdown files under `data/wiki/`
are generated exports, not read surfaces.

| Component | Path | Role |
|---|---|---|
| FastAPI server | `src/kb/web/` | REST API over Postgres; write-gated endpoints (queue, pages, dashboard, promote/approve/reject) |
| Dev script | `scripts/dev-web.sh` | Start FastAPI (`:8765`) |

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

- 2026-06-04: Postgres is now the sole source of truth; SQLite (`state.db`) removed. Reads go directly to Postgres via `psql`; writes go through the FastAPI API. `data/` is a generated Markdown export, not canonical.
- 2026-06-04: Added DB-canonical target direction; Markdown/Git flow is now documented as legacy/current rather than the end state.
- 2026-05-20: Removed workflow docs from the active documentation map; project skills are the runtime workflow layer.
- 2026-05-20: Reframed workflow docs as design references and `.claude/skills/` as runtime operating instructions.
- 2026-05-20: Added Web Review Console section (FastAPI + React SPA, `src/kb/web/`, `frontend/`, `scripts/dev-web.sh`).
- 2026-05-19: Added `data/rejected/` memory layer; noted `review_status` on six in-scope wiki types.
- 2026-05-18: Initial architecture overview after docs restructuring.
