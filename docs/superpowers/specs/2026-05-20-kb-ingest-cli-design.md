# KB Ingest CLI — Design Spec

**Date**: 2026-05-20
**Status**: Draft (brainstorming complete, awaiting user review)

## 1. Problem

`data/raw/` 와 `data/handoffs/` 에 있는 파일이 `data/wiki/` 페이지로 흡수(ingest)되었는지 git/grep만으로 판단하기 힘들다. 구체적으로 다음 4개 질문이 자주 발생한다:

- "이 raw/handoff 파일이 어떤 wiki 페이지에 인용됐나?"
- "이 파일은 한 번이라도 processing 됐나?"
- "이번 달 ingest 되지 않은 raw/handoff 는 무엇인가?" (daily 워크플로우용)
- "기간별 ingest 현황 요약은?" (audit)

현재 frontmatter 만으로는 4개 질문 거의 답이 불가능: raw 는 immutable 이라 사후 필드 추가 금지, handoff 의 `status: consumed` 는 "어디로" 정보가 없음, wiki 의 `sources:` 는 정방향(wiki → source) 만 보유.

## 2. Goals

1. 위 4개 질문에 < 1초 안에 답하는 CLI 도구 제공.
2. **Source of truth 는 그대로**: wiki 의 `sources:` 필드. 새 DB/manifest 도입 없음.
3. 기존 `_store.iter_pages` 인프라 재사용 — 신규 의존성 0.
4. raw immutability rule 위배 없음.

## 3. Non-goals

- raw/handoff 에 backref 필드 추가 (raw 는 immutable, handoff 는 sync drift 문제).
- SQLite/JSON manifest 도입 — 현재 규모(40 files)에선 YAGNI. 1000 files 까지 sub-second 예측.
- History 추적 — "언제 ingest 됐나" 는 `git log` 의 역할.
- Web UI — CLI 만 제공. 필요 시 추후 `/api/ingest` 추가.

## 4. Scope

### 입력
- `data/wiki/**/*.md` — frontmatter 의 `sources:` 필드 (이미 lint 가 강제)
- `data/raw/**/*.md`, `data/handoffs/**/*.md` — 파일 시스템 존재 여부

### 출력
사람이 읽는 표 형식 텍스트 (다른 도구로 파싱 안 함 — 필요해지면 `--json` 옵션 추가).

### 적용 대상
- 인용 대상: `raw/...`, `handoffs/...` 경로로 시작하는 모든 `sources:` 항목
- 비대상: `wiki/...` 내부 cross-link (별도 lint 가 다룸), 외부 URL

## 5. Core Algorithm

```python
def build_citation_map(wiki_dir: Path) -> dict[str, list[str]]:
    """Scan wiki, return source_path → [wiki_stems] inverse map."""
    inverse = defaultdict(list)
    for page in _store.iter_pages(wiki_dir):     # 기존 함수 재사용
        for src in page.fm.get("sources") or []:
            inverse[str(src).strip()].append(page.stem)
    return inverse

def list_filesystem(root: Path, since: date | None) -> list[Path]:
    """Return all *.md under root, optionally filtered by frontmatter 'created'."""
```

3개 CLI 명령은 위 두 함수 + 출력 포매팅 조합.

## 6. CLI Commands

### `kb-ingest status <path>`

특정 raw/handoff 파일을 인용하는 wiki 페이지 목록.

```
$ kb-ingest status handoffs/2026/05/.../docs_claude_code_handoff_02.md
cited by 1 page:
  improvements/2026-05/KB_Usage_Report_Restructure_Blockers.md  (pending_for_approve)
```

미인용 시:
```
not cited by any wiki page.
```

### `kb-ingest pending [--type raw|handoff|all] [--since YYYY-MM-DD]`

인용 0회인 파일 목록. daily 워크플로우의 "아직 처리 안 한 것" 큐.

```
$ kb-ingest pending --type handoff --since 2026-05-01
20 of 27 handoffs uncited since 2026-05-01:
  2026-05-12  handoffs/2026/05/cerebro-hitl-prd/opencode_handoff_03.md
  2026-05-11  handoffs/2026/05/cerebro-hitl-prd/opencode_handoff_02.md
  ...
```

정렬: `created` desc (없으면 file mtime).

### `kb-ingest report [--since YYYY-MM-DD]`

기간 집계.

```
$ kb-ingest report --since 2026-05-01
period: 2026-05-01 → 2026-05-20

raw:       0 files     0 cited      —
handoff:   27 files    7 cited      (26%)
                       20 uncited

wiki:      13 pages    (10 approved, 2 pending, 1 not_processed)
distinct sources cited:  7

top-cited:
  1x  handoffs/2026/05/kb-docs-usage-report-restructure/docs_claude_code_handoff_02.md
  1x  handoffs/2026/05/kb-docs-usage-report-restructure/docs_opencode_handoff_01.md
```

## 7. Implementation Structure

```
src/kb_mcp/cli/ingest/
├── __init__.py     ← argparse, main() — ~60 LOC
├── _scan.py        ← build_citation_map, list_filesystem — ~50 LOC
└── _commands.py    ← cmd_status, cmd_pending, cmd_report — ~140 LOC
```

`pyproject.toml`:
```toml
[project.scripts]
kb-ingest = "kb_mcp.cli.ingest:main"
```

기존 `kb_mcp.cli.wiki_review._store.iter_pages` 재사용. 신규 외부 의존성 0.

## 8. Edge Cases

- **`sources:` 항목이 실제 존재 안 함**: lint #8 "Stale sources" 가 이미 잡음. ingest CLI 는 그대로 인용으로 카운트 (frontmatter = truth).
- **경로 표기 변형**: `handoffs/2026/05/foo.md` vs `./handoffs/...` vs 절대경로. → `Path(src).as_posix()` 로 정규화. 앞 `./` strip.
- **wiki 페이지 자기 인용**: `sources:` 에 wiki/ 경로가 있는 경우 → ingest CLI 무시 (raw/handoffs 만 대상).
- **`created` 없는 파일**: `--since` 비교 시 frontmatter `created` 우선, 없으면 file mtime 사용. 둘 다 못 얻으면 (이론상 발생 어려움) 필터 통과시키고 출력 날짜 컬럼은 `?` — false negative 방지가 안전한 기본값.
- **빈 `sources:`**: `[]` 또는 `null` 모두 안전 처리.

## 9. Tests

- `_scan.build_citation_map`: 다중 sources, 빈 sources, 누락 sources 케이스
- `cmd_status`: 인용 있음/없음/잘못된 경로
- `cmd_pending`: 필터 (`--type`, `--since`), 정렬, 0건
- `cmd_report`: 카운트 정확성, top-N tie-break, 빈 KB

총 ~12개 신규 테스트 예상.

## 10. Escalation Trigger

다음 조건 중 하나라도 발생하면 sqlite derived index 로 escalation 검토:

1. 어떤 `kb-ingest` 명령이 P95 > 1초
2. 사용자가 JOIN/aggregation SQL 표현력이 필요한 구체 쿼리를 3개 이상 요청
3. raw/handoff 파일 합계가 5000 개 초과

그 전까지는 in-memory scan 유지.

## Appendix

### A. 왜 raw frontmatter 에 `ingested_into:` 안 추가하는가

CLAUDE.md 강한 규칙: "Never modify files in `data/raw/`. They are immutable after creation." lint 의 `--check-immutability` 가 git-status 변화 + `captured_at` vs mtime 검사로 강제. 사후 필드 추가 = rule 위반 + lint fail.

### B. 왜 handoff 에 `consumed_by:` 안 추가하는가

handoff 는 mutable 하므로 기술적으로 가능. 다만 wiki 의 `sources:` 와 양방향 sync 의무 발생 — 한쪽 갱신 빼먹으면 drift. 현재 design 은 wiki 가 forward 책임 단독 보유. 한 쪽이 truth 인 게 단순.

### C. PatchNote

- 2026-05-20: Initial spec.
