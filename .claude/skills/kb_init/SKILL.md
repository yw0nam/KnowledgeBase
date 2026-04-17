---
name: kb_init
description: KnowledgeBase 초기 설정 스킬. raw/ 소스를 처음 넣은 후 전체 그래프 빌드, wiki 전체 작성, lint, log, commit을 순서대로 실행한다. 사용자가 `/kb_init`을 입력하거나 "KnowledgeBase 처음 설정", "wiki 처음 만들어줘", "초기화해줘" 등을 요청할 때 사용한다.
---

# kb_init

KnowledgeBase 초기 설정. 처음 raw/ 소스를 넣었을 때 한 번 실행.
그래프 빌드 → wiki 전체 작성 → lint → log → commit.

## Steps

### Step 1 — 구조 확인

필요한 디렉토리가 없으면 생성:

```bash
mkdir -p data/raw/github/claude-md data/raw/github/issues data/raw/manual
mkdir -p data/wiki/entities data/wiki/concepts data/wiki/summaries data/wiki/decisions data/wiki/questions
touch data/log.md 2>/dev/null || true
```

### Step 2 — 그래프 빌드

```bash
cd data
```

이후 Skill 도구를 사용해 graphify 스킬을 호출한다:
- skill: `"graphify"`
- args: `"raw/ --no-viz"`

(init이므로 `--update` 없이 전체 추출. bash로 실행하지 말 것.)

Note: graphify 스킬을 여러번 로드하고있다면 잘못하고있는것이다. 유저에게 반드시 문의할것, 문의하지않으면 계속 잘못된 graphify 스킬이 로드되어 문제가 발생할 것이다.

### Step 3 — wiki 전체 작성

> **반드시 `references/wiki_templates.md`를 먼저 읽고 시작한다.**
> 모든 wiki 페이지는 해당 템플릿을 정확히 따른다.

`data/graphify-out/graph.json`을 읽어 노드/엣지/커뮤니티 파악.
`data/raw/` 전체 파일 목록을 확인하고 wiki 페이지를 작성한다.

**페이지 종류별 위치:**

- entity 페이지: `data/wiki/entities/{subject}/{YYYY-MM}/PascalCase.md`
  - subject는 raw 파일의 repo 이름 (e.g. `DesktopMatePlus`) 또는 주제
  - `{YYYY-MM}`은 raw frontmatter의 `created_at` 또는 `captured_at`에서 추출
- concept 페이지: `data/wiki/concepts/Snake_Case.md`
  - graph.json의 hyperedge 또는 여러 entity에 걸친 공통 패턴
- subject hub: `data/wiki/entities/{subject}/_index.md`
  - subject 아래 모든 entity 페이지 목록

### Step 4 — Lint

```bash
uv run python3 scripts/lint-wiki.py
```

ERROR가 있으면 수정 후 재실행. PASSED 확인 후 다음 단계.

### Step 5 — Log

`data/log.md`에 append:

```markdown
## {YYYY-MM-DD} kb_init | {처리한 소스 요약}

- Processed N raw files
- Created X wiki pages (entities: N, concepts: N)
- Lint: PASSED
```

### Step 6 — Commit

```bash
cd data && git add raw/ wiki/ log.md && git commit -m "init: KnowledgeBase wiki generated"
```
