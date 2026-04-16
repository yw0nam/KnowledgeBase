---
name: kb_search
description: KnowledgeBase 지식 그래프 기반 질문 답변 스킬. data/graphify-out/graph.json을 traversal해 답변을 생성한다. 사용자가 `/kb_search <질문>`을 입력하거나 KnowledgeBase에 저장된 내용에 대해 "~가 뭐야", "~는 어떻게 연결돼", "~에 대해 알려줘" 등을 요청할 때 사용한다.
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
