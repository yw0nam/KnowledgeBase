# Architecture

Updated: 2026-05-18

## 1. Synopsis

- **Purpose**: Explain the KnowledgeBase repository layout, data boundaries, and memory layers.
- **I/O**: Repository path or data file -> correct layer, owner, and mutation rule.

## 2. Core Logic

### Repository Boundary

KnowledgeBase has two git repositories:

| Repo | Path | Purpose | Push Policy |
|---|---|---|---|
| Outer repo | `KnowledgeBase/` | Code, docs, templates, lint tools | Public-safe |
| Nested repo | `data/` | Raw sources, wiki, handoffs, logs | Local-only |

Never commit `data/` contents to the outer repository. The outer `.gitignore` excludes `data/`.

### Memory Layers

| Layer | Path | Meaning | Mutation Rule |
|---|---|---|---|
| Raw | `data/raw/` | Captured source evidence | Create only; never edit existing files |
| Handoffs | `data/handoffs/` | Operational state and agent handoff | Update during tasks and periodic runs |
| Wiki | `data/wiki/` | Durable long-term knowledge | Update only with source-backed frontmatter |
| Rejected | `data/rejected/` | Wiki pages rejected during review (audit trail) | Populated only by `kb-wiki-review reject`; mirrors `wiki/` tree |
| Log | `data/log.md` | Append-only operation history | Append every operation |
| Templates | `templates/` | File skeletons | Update in outer repo |
| Docs | `docs/` | Operating instructions and references | Update in outer repo |

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

Six of the seven types (`entity`, `concept`, `decision`, `improvement`, `checklist`, `question`) carry a `review_status` field (`not_processed` → `pending_for_approve` → `approved`) managed via `kb-wiki-review`. Summaries are exempt. Only `approved` pages appear in `INDEX.md`. See `docs/workflows/wiki-approval-workflow.md`.

### Operating Flow

The default flow is:

```text
data/raw/ -> data/wiki/ -> data/log.md -> lint -> data repo commit
```

Handoffs sit beside the flow as the operational state board. They record what was processed, what is blocked, and what the next agent should do.

## 3. Usage

When deciding where information belongs:

| Information | Put It In |
|---|---|
| External source capture | `data/raw/` |
| Current task state or next action | `data/handoffs/` |
| Durable concept or entity | `data/wiki/` |
| Execution record | `data/log.md` |
| Reusable file skeleton | `templates/` |
| Agent operating instruction | `docs/workflows/` |
| Schema or command reference | `docs/reference/` |

---

## Appendix

### A. PatchNote

- 2026-05-19: Added `data/rejected/` memory layer; noted `review_status` on six in-scope wiki types.
- 2026-05-18: Initial architecture overview after docs restructuring.
