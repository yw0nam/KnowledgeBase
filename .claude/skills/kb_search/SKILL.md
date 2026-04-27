---
name: kb_search
description: KnowledgeBase 지식 그래프 기반 질문 답변 스킬. data/graphify-out/graph.json을 traversal해 답변을 생성하고, 사용자 확인 시 답변을 wiki/questions/ 에 저장한다. 사용자가 `/kb_search <질문>`을 입력하거나 KnowledgeBase에 저장된 내용에 대해 "~가 뭐야", "~는 어떻게 연결돼", "~에 대해 알려줘" 등을 요청할 때 사용한다.
---

# kb_search

KnowledgeBase 지식 그래프 기반 질문 답변.
`data/graphify-out/graph.json`을 traversal해 답변을 생성한다.

## Usage

```
/kb_search <질문>
```

## Steps

### Step 1 — 그래프 존재 확인

```bash
test -f data/graphify-out/graph.json && echo "OK" || echo "NOT_FOUND"
```

`NOT_FOUND`이면: "`/kb_init`을 먼저 실행해 그래프를 빌드하세요." 출력 후 종료.

### Step 2 — 그래프 traversal

`scripts/graph_query.py`를 직접 실행한다 (graphify 스킬 호출 불필요):

```bash
# BFS — "X는 무엇과 연결되나" 같은 넓은 컨텍스트 질문
python3 scripts/graph_query.py "<질문>" --graph data/graphify-out/graph.json

# DFS — 특정 경로를 따라가야 할 때
python3 scripts/graph_query.py "<질문>" --dfs --graph data/graphify-out/graph.json
```

BFS/DFS 선택 기준:
- BFS: "X가 뭐야", "X 관련 PR", "X와 연결된 것" — 넓은 탐색
- DFS: "X에서 Y까지 어떻게 연결돼", "X의 구현 경로" — 깊은 추적

### Step 3 — 답변 합성

traversal 결과를 바탕으로 답변 작성:

- graph에 있는 정보만 사용. 없으면 "그래프에 해당 정보가 없습니다" 명시.
- 관련 wiki 페이지가 있으면 `[[WikiPageName]]` 형식으로 참조.
- 출처가 있는 사실은 raw 파일 경로 인용 (`source_file`).
- 답변 끝에 자연스러운 후속 질문 하나 제안.

### Step 4 — 답변 저장 (사용자 확인 후)

답변 출력 후 사용자에게 묻는다:

```
이 답변을 wiki/questions/ 에 저장할까요?
```

사용자가 `yes` / `저장해` / `save` 답하면 `data/wiki/questions/<PascalCaseSlug>.md` 작성. 아니라고 하거나 답이 없으면 저장하지 않고 종료.

Slug 규칙: 질문 핵심을 PascalCase 영어로 5단어 이내. 한글 질문이면 LLM이 의미 추출해 영어 PascalCase로 변환. 예: "TTS 파이프라인 어떻게 구현됐어?" → `TTSPipelineImplementation.md`. 다른 KB 페이지처럼 PascalCase.

frontmatter (block-style YAML, dates quoted, scalars unquoted):

```yaml
---
type: question
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources:
  - raw/...        # traversal에서 만난 raw 파일들 (graph node의 source_file)
aliases: []
tags:
  - question
---
```

body 구조:

```markdown
# {원본 질문}

## 답변
[답변 본문]

## Related
- [[WikiPageA]]
- [[WikiPageB]]

## Sources
- raw/github/issues/...
```

저장 후 lint를 따로 돌리지 않음 (다음 kb_update가 처리). 저장 후 한 줄 출력: `저장됨: data/wiki/questions/<Slug>.md`

저장된 페이지는 이후 `find_start_nodes`의 wiki expansion(kb_search 보강 후)에서 picked up되어, 다음 검색의 entry point로 작동한다.

### 답변 형식

```
**답변**
[내용]

**관련 페이지**
- [[PageName]]

**출처**
- raw/github/issues/repo_42.md

**더 알아보기**
> [후속 질문 제안]
```
