# Workflows (At-a-Glance Map)

Updated: 2026-06-02

## 1. Synopsis

- **Purpose**: Give a one-look mental model of how KnowledgeBase moves: what the
  nightly automation does, how a raw source becomes an approved wiki page, and how
  private data reaches `master`.
- **Scope**: Overview only. This is **not** an execution guide — every cron job's
  behavior is governed by a skill. For step-level detail, read the relevant
  `.claude/skills/<name>/SKILL.md` (see [§5](#5-where-the-detail-lives)).

## 2. Legend

The same conventions apply to every diagram below:

| Style | Meaning |
|---|---|
| 🟦 blue box | **Deterministic** job — pure CLI (`uv run kb-*`), no LLM |
| 🟪 purple box | **LLM-driven** job — runs `opencode run` against a skill contract |
| ⬦ diamond | **Gate / decision** (e.g. lint pass?) — blocks the flow on failure |
| 👤 | **Human-run** step (not a cron job) |
| dashed arrow | read-only / report (no artefact produced or moved) |

## 3. Nightly cron pipeline (KST)

The whole night collapses to: *collect → organize → DB write + export*,
with a separate morning read-out to Slack.

```mermaid
flowchart LR
  classDef det fill:#e3f2fd,stroke:#1565c0,color:#0d47a1;
  classDef llm fill:#f3e5f5,stroke:#6a1b9a,color:#4a148c;
  classDef ext fill:#fff8e1,stroke:#f9a825,color:#5d4037,stroke-dasharray:4 3;
  classDef gate fill:#ffffff,stroke:#555,color:#000;

  ttl["00:30<br/>wiki-ttl-sweep"]:::det
  subgraph R["03:10–03:20 · usage reports"]
    direction TB
    oc["opencode"]:::det
    hm["hermes"]:::det
    cc["claude-code"]:::det
  end
  mem["03:30<br/>memory-daily"]:::llm
  prom["04:00<br/>wiki-promote"]:::llm
  wrap["05:00<br/>cron-wrapup"]:::llm
  papers["10:05<br/>ingest-daily-papers"]:::det
  slack["09:00 · morning-slack-digest 👤<br/>(Hermes agent — not a KB cron)"]:::ext
  Slack[("Slack")]

  wk["04:15 memory-weekly<br/>(Mon)"]:::llm
  mo["04:45 memory-monthly<br/>(1st)"]:::llm

  ttl --> R --> mem --> prom --> wrap
  prom -. "Mon" .-> wk -.-> wrap
  prom -. "1st" .-> mo -.-> wrap
  wrap -. "reads committed wrap-up" .-> slack -.-> Slack
  papers
```

Intuition: nothing pushes mid-night — `cron-wrapup` (05:00) writes the night's
work through the DB API as one checkpoint. `ingest-daily-papers` (10:05) and the
`morning-slack-digest` (09:00, runs with the Hermes agent) sit outside the main chain.

## 4. Data flow & review lifecycle

How a captured source becomes durable, indexed knowledge — and what `INDEX.md` lists.

```mermaid
flowchart TB
  classDef raw fill:#eceff1,stroke:#546e7a,color:#263238;
  classDef state fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
  classDef term fill:#ffebee,stroke:#c62828,color:#b71c1c;

  src["sources<br/>github · chat · calendar · web · manual"]
  raw["data/raw/<br/>immutable · create-only"]:::raw
  auth["wiki-authoring / memory-report<br/>write page"]
  np(["not_processed"]):::state
  pend(["pending_for_approve"]):::state
  appr(["approved"]):::state
  idx["wiki/INDEX.md<br/>(approved pages only)"]
  rej["rejected/<br/>audit trail"]:::term
  ttl["TTL sweep (7d)<br/>→ expire"]:::term

  src --> raw --> auth --> np
  np -- "wiki-promote" --> pend
  pend -- "👤 approve" --> appr --> idx
  pend -- "reject" --> rej
  np -. "stale" .-> ttl
  pend -. "stale" .-> ttl
```

Intuition: `data/raw/` is write-once evidence; wiki pages climb an approval ladder
(`not_processed → pending_for_approve → approved`), and only **approved** pages land
in `INDEX.md`. Stale unprocessed/pending pages are swept by TTL; explicit rejections
are kept as an audit trail.

## 5. Two-repo sync (deprecated)

> The legacy git-based sync model (work branch → PR → merge) is deprecated
> following the DB-canonical migration. See `docs/db-canonical.md` for the
> current architecture.

## 6. Where the detail lives

This map is intentionally shallow. Each job's real contract — inputs, outputs, lint
order, edge cases — lives in its skill:

- LLM-driven jobs load their behavior from a `SKILL.md` at runtime
  (`memory-*` → `memory-report`; `wiki-promote` → `wiki-approval`;
  `cron-wrapup` → `cron-wrapup`).
- Deterministic jobs are CLIs, but their setup and operating contract are still
  documented in skills (e.g. usage reports → `usage-report-setup`).
- The legacy sync model (work branch → PR → merge) was owned by the `data-sync` skill (deprecated; see `docs/db-canonical.md`).

Browse `.claude/skills/` for the full set; read the matching `SKILL.md` for any box
in the diagrams above.
