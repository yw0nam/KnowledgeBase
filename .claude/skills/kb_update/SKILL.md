---
name: kb_update
description: KnowledgeBase 증분 업데이트 스킬. ingest로 raw/ 파일이 추가된 후 그래프 증분 업데이트, 새 파일만 wiki 작성(병렬 sub-agent), lint, log, commit을 순서대로 실행한다. 사용자가 `/kb_update`를 입력하거나 "새로 추가된 파일 wiki에 반영해줘", "wiki 업데이트해줘", "ingest 했는데 wiki 써줘" 등을 요청할 때 사용한다.
---

# kb_update

ingest 이후 새로 추가된 raw 파일을 wiki에 반영.
그래프 증분 업데이트 → 새 파일만 wiki 작성(병렬 sub-agent) → lint → log → commit.


## Steps

### Step 1 — 변경 파일 파악

```bash
cd data
git -C . status --short
```


변경 파일이 없으면 "처리할 새 파일이 없습니다" 출력 후 종료.
새 raw 파일 목록을 내부적으로 기록해둔다 (Step 3에서 사용).

### Step 2 — 그래프 증분 업데이트


/graphify raw/ --update --no-viz

### Step 3 — wiki 업데이트 (병렬 sub-agent)

> **컨텍스트 절약을 위해 파일별로 sub-agent를 병렬 dispatch한다.**
> Main agent는 orchestration과 `_index.md` 업데이트만 담당한다.

#### 3-1. Sub-agent 병렬 dispatch

Step 1에서 파악한 새/변경 raw 파일을 **최대 10개씩 묶어** Agent 도구로 dispatch한다.
파일이 10개 이하면 sub-agent 1개, 11~20개면 2개, 이런 식으로 올림 처리한다.
독립적인 batch는 **한 번의 메시지에 여러 Agent 도구 호출**로 동시에 실행한다.

각 sub-agent의 prompt (아래 템플릿을 실제 값으로 채워 전달):

```
You are a wiki writer for a personal knowledge base. You are a subagent — do NOT use any skills, do NOT invoke graphify, just follow these instructions directly.

Today's date: {YYYY-MM-DD}
KnowledgeBase root: ./
Data directory: ./data

## Your task

Process these raw files and write their wiki entity pages.

Raw files:
{absolute_raw_file_path_1}
{absolute_raw_file_path_2}
...
(up to 10 files)

## Steps

1. Read each raw file in the list above.
2. Read graphify-out/graph.json — for each file, find nodes and edges where source_file matches it. Use those relationships to populate the Relationships section.
3. For each file, create or update the wiki entity page:
   - New: wiki/entities/{subject}/{YYYY-MM}/PascalCase.md  (derive subject from repo name or content)
   - Update: refresh `updated:` date, append to `sources:` if not already present
4. If a related concept page already exists in wiki/concepts/, update it. Do NOT create new concept pages.
5. Do NOT touch _index.md files.
6. Do NOT commit anything.
7. Report the exact file paths you created or updated.

## Frontmatter rules

- Dates quoted: `"2026-04-20"`
- Scalars unquoted: `type: entity` (not `type: "entity"`)
- Lists block style only: `sources:\n  - path` (not `sources: [path]`)
- `sources:` — only real existing raw file paths
- Wikilinks: [[FileName]] or [[FileName|Display Text]] — no .md extension
- Never link to pages that do not exist — use plain text instead

## Entity page format

```markdown
---
type: entity
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources:
  - raw/github/issues/repo_42.md
aliases: []
tags: []
---

# Page Title

## Overview

[1-2 paragraph summary from the raw source.]

## Key Details

[Technical details, implementation, architecture, etc.]

## Relationships

- [[RelatedPage|Related Page Title]] (relation type)
```
```

#### 3-2. _index.md 업데이트

모든 sub-agent 완료 후, main agent가 영향받은 각 subject의 `_index.md`를 업데이트한다.

- `wiki/entities/{subject}/_index.md` 없으면 새로 생성
- 새 entity 페이지를 적절한 카테고리 섹션 아래 wikilink로 추가
- **각 링크에 반드시 한 줄 설명을 추가한다** (`— 설명` 형식, 한국어)
- 페이지가 10개 이상인 subject는 기능 영역별로 섹션을 나눈다
- 형식:

```markdown
---
type: entity
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources: []
aliases: []
tags:
  - project
---

# Subject Name

> [2-3줄 프로젝트/주제 설명. 무엇을 다루는지, 핵심 기술/범위.]

## Pages

### YYYY_MM

#### Category Name (페이지 10개 이상일 때 기능별 그룹핑)

- [[PascalCasePage|Page Title]] — 이 페이지의 핵심 내용 한 줄 설명

### YYYY_MM (페이지 10개 미만일 때 카테고리 없이 월만)

- [[PascalCasePage|Page Title]] — 이 페이지의 핵심 내용 한 줄 설명
```

**구조 규칙:**
- 월 헤더는 항상 `### YYYY_MM` (언더스코어 사용, 하이픈 아님)
- 페이지 10개 이상: 월 아래에 `#### Category` 섹션으로 기능별 그룹핑
- 페이지 10개 미만: 월 아래에 카테고리 없이 링크 나열

**한 줄 설명 작성 규칙:**
- 제목을 반복하지 않는다 ("PR11 TTS Pipeline — TTS 파이프라인" ❌)
- 실제 변경 내용이나 핵심 결정을 담는다 ("POST /v1/tts/speak 엔드포인트 신설" ✅)
- 15~35자 내외

### Step 4 — Lint

```bash
uv run python3 scripts/lint-wiki.py
```

ERROR가 있으면 수정 후 재실행. PASSED 확인 후 다음 단계.

### Step 5 — Log

`log.md`에 append:

```markdown
## {YYYY-MM-DD} kb_update | {처리한 소스 요약}

- New raw files: N
- Created: X pages, Updated: Y pages
- Lint: PASSED
```

### Step 6 — Commit

```bash
cd data && git add raw/ wiki/ log.md && git commit -m "update: {소스 이름} wiki synced"
```
