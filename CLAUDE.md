# KnowledgeBase

Personal LLM wiki backed by handoff system. Raw sources go in, LLM writes wiki pages, lint validates.

## Overview

KnowledgeBase is a memory-workflow system (v0) that captures knowledge from multiple sources, organizes it into a structured wiki, and maintains operational records via handoff documents. The system separates code (outer repo) from operational data (nested `data/` repo).

## Repository Layout

```
KnowledgeBase/                    # Outer repo: code, lint, templates, docs
├── src/kb_mcp/                   # CLI tools + FastAPI web server
│   ├── cli/
│   │   ├── lint_wiki.py          # kb-lint-wiki command
│   │   ├── lint_handoff.py       # kb-lint-handoff command
│   │   └── wiki_index.py         # kb-wiki-index command (regen wiki/INDEX.md)
│   └── web/                      # FastAPI review console backend (kb-web)
│       ├── app.py                #   FastAPI app factory
│       ├── config.py             #   KB_DATA_DIR, port config
│       ├── main.py               #   kb-web entrypoint
│       └── routes/               #   /api/queue, /api/pages, /api/dashboard
├── src/CLAUDE.md                 # CLAUDE.md file for src/
├── frontend/                     # Vite + React + TypeScript review console SPA
│   ├── src/                      #   Pages (QueuePage, DashboardPage), components, API clients
│   └── ...
├── scripts/
│   ├── ingest-github.sh          # GitHub source collection
│   └── dev-web.sh                # Start FastAPI + Vite together
├── templates/                    # Frontmatter + handoff templates
│   ├── wiki/                     #   Wiki page templates (entity, concept, decision, …)
│   │   └── summaries/            #     Summary subtypes (daily, weekly, …)
│   ├── handoff/                  #   Handoff templates (task, final, readme)
│   └── raw/                      #   Raw source frontmatter
├── pyproject.toml
├── CLAUDE.md                     # This file
├── README.md
├── docs/
│   ├── CLAUDE.md                 # CLAUDE.md file for docs/
│   ├── README.md                 # Documentation index
│   ├── architecture.md           # Repository and memory layer map
│   ├── workflows/                # Operating procedures
│   │   ├── cron-jobs.md          # Cron schedule, wrappers, and failure policy
│   │   ├── handoff-system.md     # Handoff system spec
│   │   ├── periodic-memory-workflow.md # Daily/weekly/monthly memory workflow
│   │   ├── usage-reports.md      # OpenCode/Hermes report modes
│   │   └── pipeline.md           # 4-stage pipeline details
│   ├── db_informations/          # DB schemas and monitoring guides
│   └── reference/                # Schemas, categories, commands
│       ├── commands.md           # Command reference
│       ├── frontmatter.md        # Frontmatter schemas
│       └── wiki-categories.md    # Wiki categories
└── .gitignore                    # Excludes data/

data/                             # Nested git repo: raw sources + wiki (local-only)
├── .git/
├── raw/
│   ├── github/
│   │   ├── claude-md/            # CLAUDE.md files ({owner}_{repo}_CLAUDE.md)
│   │   └── issues/               # Issues + PRs ({repo}_{number}.md)
│   ├── conversations/            # Desktop Chatbot history ({YYYY-MM}/chat_{timestamp}.md)
│   ├── calendar/                 # Calendar events ({YYYY-MM}/event_{date}_{slug}.md)
│   ├── web/                      # Web clippings
│   └── manual/                   # Hand-dropped files
├── handoffs/                     # Handoff documents (task-based)
├── wiki/
│   ├── entities/                 # Named objects ({subject}/{YYYY-MM}/)
│   ├── concepts/                 # Abstract ideas (flat)
│   ├── decisions/                # Architecture Decision Records
│   ├── questions/                # Saved Q&A
│   ├── improvements/             # Open-ended improvements (NEW)
│   ├── checklists/               # Operational checklists (NEW)
│   └── summaries/                # Time/subject rollups (daily/weekly/monthly/migration)
└── log.md                        # Append-only operation record
```

## Pipeline

4-stage pipeline: Ingest → Fill → Log → Lint.

```
1. INGEST → 2. FILL → 3. LOG → 4. LINT
(script)    (LLM)    (LLM)   (script)
```

See [Pipeline details](docs/workflows/pipeline.md) for stage-by-stage actions and lint check categories.

## Important Rules

- Never modify files in `data/raw/`. They are immutable after creation. Use `kb-lint-wiki --check-immutability` to enforce: git-status must not show modifications, `captured_at` must be ≤ file mtime (60s tolerance), and required raw frontmatter fields (`source_url`, `type`, `captured_at`, `contributor`) are always validated.
- `data/wiki/` pages must always list their `sources:` in frontmatter.
- Keep `data/log.md` updated on every operation.
- Lint must pass (0 errors) before committing wiki changes.
- Handoff documents are stored in `data/handoffs/` and tracked via git.
- Use uv for package management

## Wiki Approval Workflow

6 wiki 페이지 타입(`entity`, `concept`, `decision`, `improvement`, `checklist`, `question`)은 `review_status` 필드를 통한 사람 승인 사이클을 거친다.

- **새 페이지 작성 (AI)**: 템플릿이 `review_status: not_processed` 를 자동 포함. AI가 직접 추가/수정할 필요 없음.
- **Approved 페이지 수정 (AI)**: semantic 변화면 `review_status` 를 `not_processed` 로 self-reset, typo/포매팅이면 유지. Deterministic 감지는 없음 — agent 판단.
- **`## User Feedback` 헤딩 예약**: CLI 전용 섹션. 일반 콘텐츠에서 이 정확한 헤딩 사용 금지. 다른 의미는 `## Feedback`, `## Reviewer Notes` 등 다른 이름 사용.
- **INDEX.md / subject `_index.md`**: 자동 동기화 없음. Approve 후 subject hub 라인 추가는 user 또는 동반 작업 agent의 책임.
- **CLI**: `uv run kb-wiki-review list / promote / approve / reject / ttl-sweep`. 상세는 `docs/workflows/wiki-approval-workflow.md`.

`improvement` 타입은 두 `_status` 필드를 보유: `review_status`(이 페이지가 승인됐는가)와 `issue_status`(추적 이슈가 open/resolved 등). 같은 prefix가 도메인을 분리.

## Privacy

`data/` is a local-only nested git repository. It is never pushed to remote.

- Outer `.gitignore` excludes `data/`
- `data/.git` is independent from outer repo
- All raw sources and wiki pages stay local
- Handoff documents (which may contain sensitive decisions) stay local

Never commit `data/` contents to the outer repository.

## Skills

- `knowledgebase-initialize` — initialize `data/`, verify tooling, and propose cron jobs for approval.

## Documentation

- [Documentation Index](docs/README.md) — read order and document map
- [Architecture](docs/architecture.md) — repository layout and memory layers
- [Pipeline](docs/workflows/pipeline.md) — 4-stage pipeline (Ingest → Fill → Log → Lint), commands, lint categories
- [Cron Jobs](docs/workflows/cron-jobs.md) — scheduling, locking, wrappers, failure policy
- [Usage Reports](docs/workflows/usage-reports.md) — OpenCode, Hermes, combined report modes
- [Periodic Memory Workflow](docs/workflows/periodic-memory-workflow.md) — daily, weekly, monthly memory workflow for cron agents
- [Frontmatter Conventions](docs/reference/frontmatter.md) — Raw, Wiki, Handoff frontmatter schemas
- [Wiki Categories](docs/reference/wiki-categories.md) — 7 categories, naming, wikilinks, tags
- [Handoff System](docs/workflows/handoff-system.md) — Roles, status, promotion, frontmatter
- [Wiki Approval Workflow](docs/workflows/wiki-approval-workflow.md) — review_status lifecycle, CLI, TTL cron
- [Commands](docs/reference/commands.md) — kb-lint-wiki, kb-lint-handoff, kb-wiki-index

## Linting

Use lint for src code before commit
```bash
./scripts/lint.sh
```
