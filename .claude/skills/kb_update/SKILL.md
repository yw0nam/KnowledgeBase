---
name: kb_update
description: KnowledgeBase 증분 업데이트 스킬. ingest로 raw/ 파일이 추가된 후 그래프 증분 업데이트, 새 파일만 wiki 작성, lint, log, commit을 순서대로 실행한다. 사용자가 `/kb_update`를 입력하거나 "새로 추가된 파일 wiki에 반영해줘", "wiki 업데이트해줘", "ingest 했는데 wiki 써줘" 등을 요청할 때 사용한다.
---

# kb_update

ingest 이후 새로 추가된 raw 파일을 wiki에 반영.
그래프 증분 업데이트 → 새 파일만 wiki 작성 → lint → log → commit.

## Steps

### Step 1 — 변경 파일 파악

```bash
git -C data/ status --short
```

`raw/` 아래 untracked(`??`) 또는 modified(`M`) 파일 목록을 확인한다.
변경 파일이 없으면 "처리할 새 파일이 없습니다" 출력 후 종료.

### Step 2 — 그래프 증분 업데이트

```bash
cd data
```

이후 Skill 도구를 사용해 graphify 스킬을 호출한다:
- skill: `"graphify"`
- args: `"raw/ --update --no-viz"`

캐시를 활용해 새 파일만 재추출. 결과: `data/graphify-out/graph.json` 업데이트.
(bash로 실행하지 말 것.)

### Step 3 — wiki 업데이트

> **반드시 `references/wiki_templates.md`를 먼저 읽고 시작한다.**
> 모든 wiki 페이지는 해당 템플릿을 정확히 따른다.

Step 1에서 파악한 새/변경 raw 파일만 처리한다. 기존 파일은 건드리지 않는다.

각 파일에 대해:
1. raw 파일 읽기
2. `data/graphify-out/graph.json`에서 해당 파일 관련 노드/엣지 확인
3. 대응하는 wiki 페이지 생성 또는 업데이트
   - 신규: `data/wiki/entities/{subject}/{YYYY-MM}/PascalCase.md`
   - 기존 페이지 업데이트 시: frontmatter `updated:` 날짜 갱신, `sources:`에 추가
4. 영향받는 concept 페이지도 업데이트 (새 entity와 연결되는 경우)
5. subject `_index.md` 업데이트

### Step 4 — Lint

```bash
uv run python3 scripts/lint-wiki.py
```

ERROR가 있으면 수정 후 재실행. PASSED 확인 후 다음 단계.

### Step 5 — Log

`data/log.md`에 append:

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
