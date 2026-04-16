# KnowledgeBase

Personal LLM Wiki. Raw sources go in, LLM writes wiki pages, lint keeps them honest.

## Structure

두 개의 git repo로 분리한다.

- **루트 repo** (`KnowledgeBase/`) — 스크립트, 설정. 공개 가능.
- **data repo** (`KnowledgeBase/data/`) — 콘텐츠. 로컬 전용, push 하지 않는다.

### data/

- `raw/` - Immutable sources. Never modify after creation. Subdirs by type:
  - `github/claude-md/` - CLAUDE.md files from repos (`{owner}_{repo}_CLAUDE.md`)
  - `github/issues/` - Issues + PRs (`{repo}_{number}.md`)
  - `conversations/` - Desktop Chatbot history (`{YYYY-MM}/chat_{timestamp}.md`)
  - `calendar/` - Calendar events (`{YYYY-MM}/event_{date}_{slug}.md`)
  - `web/` - Web clippings (Obsidian Web Clipper output)
  - `manual/` - Anything dropped by hand
- `wiki/` - LLM-generated pages. Subdirs:
  - `entities/{project}/{YYYY-MM}/` - Project entities grouped by project and month
  - `entities/{project}/_index.md` - Project hub page
  - `entities/misc/` - Non-project entities (people, tools)
  - `concepts/` - Abstract ideas, cross-cutting (flat, no subdirs)
  - `summaries/` - Time/project rollups (weekly/, monthly/, projects/)
  - `decisions/` - Architecture Decision Records
  - `questions/` - Saved Q&A
- `log.md` - Append-only chronological record of operations.

## Conventions

### Frontmatter - Raw files

```yaml
---
source_url: "https://..."
type: "github_issue" | "claude_md" | "conversation" | "calendar_event" | "web_article" | "manual"
captured_at: "2026-04-15T09:00:00Z"
author: "who wrote it"
contributor: "who added it"
tags: []
---
```

### Frontmatter - Wiki pages

Always use YAML block style for lists. Never quote scalar values except dates.

```yaml
---
type: entity
created: "2026-04-15"
updated: "2026-04-15"
sources:
  - raw/github/issues/repo_42.md
aliases: []
tags: []
---
```

### Naming

- Raw: `{repo}_{issue_number}.md`, `chat_{ISO_timestamp}.md`, `event_{date}_{slug}.md`
- Wiki entities: `{project}/{YYYY-MM}/PascalCase.md` (e.g. `DesktopMatePlus/2026-04/PR36_HumanInTheLoopApprovalGate.md`)
- Wiki project hub: `{project}/_index.md` (lists all pages by month)
- Wiki concepts: Snake_Case, flat (`Agent_Middleware_Implementation_Stack.md`)
- Wiki summaries: ISO date/week (`2026-W16.md`, `2026-04.md`)

### Wikilinks (Obsidian)

- Use `[[FileName]]` or `[[FileName|Display Text]]`. Never include `.md` extension.
- Only link to pages that exist. If a concept has no wiki page, use plain text.
- Raw sources are cited in frontmatter `sources:` array, never as inline links.

### Tags

Flat namespace. Common: project, tool, pattern, decision, person, event.

## Pipeline

3단계 파이프라인.

```
1.INGEST → 2.FILL → 3.LINT → 4.LOG
(스크립트)   (LLM)  (스크립트)  (LLM)
```

### 1. Ingest — 데이터 수집

```bash
./scripts/ingest-github.sh owner/repo    # GitHub CLAUDE.md + Issues + PRs
# 또는 raw/manual/ 에 직접 드롭
```

결과: `raw/{type}/` 에 frontmatter 포함 마크다운 파일.

### 2. Fill — LLM이 wiki 작성

`git -C data/ status`로 새로 추가된 raw 파일 파악 후 처리한다.

- 각 raw 파일을 읽고 관련 wiki 페이지를 새로 만들거나 업데이트
- frontmatter의 `sources:` 는 반드시 실제 raw 파일 경로를 기입
- 존재하는 페이지에만 wikilink 사용

### 3. Lint — 검증

```bash
uv run python3 scripts/lint-wiki.py               # errors만 실패
uv run python3 scripts/lint-wiki.py --strict      # warnings도 실패
```

검사 항목 (ERROR = 커밋 불가):

- Dead wikilinks, `.md` in target, LaTeX/HTML, frontmatter format,
  stale sources, missing frontmatter

검사 항목 (WARN = 정보):

- Self-links, unfilled placeholders, orphan pages, empty sections

### 4. Log — 기록

LLM이 `log.md`에 append. lint PASSED 후에만 기록.

## Important rules

- Never modify files in `raw/`. They are immutable after creation.
- `wiki/` pages must always list their `sources:` in frontmatter.
- Keep `data/log.md` updated on every operation.
- Lint must pass (0 errors) before committing wiki changes.

## Scripts

| 스크립트 | 역할 | 단계 |
|---|---|---|
| `scripts/ingest-github.sh` | GitHub 소스 수집 | 1. Ingest |
| `scripts/lint-wiki.py` | 검증 | 3. Lint |
