# Wiki Approval Workflow — Design Spec

**Date**: 2026-05-19
**Status**: Approved (brainstorming complete, ready for implementation plan)

## 1. Problem

AI 에이전트가 `data/wiki/` 에 마크다운 페이지를 직접 작성하면, 검증되지 않은 콘텐츠가 곧바로 "공식 wiki"로 합류한다. 결과적으로:

- 잘못된/저품질 콘텐츠가 silently 누적
- AI agent가 다른 작업에서 wiki를 참고할 때 잡음을 사실로 취급
- 사용자가 wiki 품질을 통제할 단일 진입점이 없음

이 spec은 AI가 쓴 wiki 페이지에 *사람 검토 단계*를 도입해 위 문제를 해결한다.

## 2. Goals

1. AI 작성 페이지는 사람 approve 전에는 "공식 wiki"로 간주되지 않음 — INDEX.md/subject hub에 등장하지 않음.
2. AI/사람의 모든 review 판단이 페이지에 audit trail로 보존되어, 나중에 거절 패턴 분석이 가능.
3. 기존 lint/index/cron 인프라에 surgical 변경만 — 새 인프라 최소화.
4. 향후 UI를 얹기 좋은 CLI 데이터 모델.

## 3. Non-goals

- Approved 페이지에 대한 AI 수정의 *deterministic* 감지/차단 — 이건 agent 판단 + CLAUDE.md 가이드라인에 위임.
- 검색 시스템 도입 — 현재 wiki 규모(11페이지)에선 YAGNI.
- 자동 promote agent의 cron 자동화 — MVP에서 contract만 정의, 호출은 사용자가 수동.
- "Unreject" 기능 — 필요하면 수동 git mv + frontmatter 편집으로 가능.

## 4. Scope

### 적용 page types (6개)

`entity`, `concept`, `decision`, `improvement`, `checklist`, `question`

### 제외 page types

- `summary` 전체 (deterministic cron 산출물 + LLM-synthesized daily memory). "LLM이 알아서 하는 곳."
- `index` (auto-generated INDEX.md).

### 비교: 기존 lifecycle 필드

| 필드 | 적용 | 의미 |
|---|---|---|
| `improvement.status` | improvement 전용 (기존) | content lifecycle: `open / acknowledged / resolved / wontfix` |
| **`review_status`** (신규) | 6 in-scope 타입 | approval lifecycle: `not_processed / pending_for_approve / approved` |
| `handoff.status` | data/handoffs/ (기존, 무관) | `draft / ready / consumed / superseded` |

세 필드는 의미가 다르며 충돌하지 않는다.

## 5. Status Model

```
[writer AI] ──creates──▶ not_processed
                              │
                              │ daily-update agent: 관련성 판단
                              │  ├─ promote ─▶ pending_for_approve
                              │  ├─ leave   ─▶ (다음 날 재고려)
                              │  └─ TTL 7d  ─▶ data/rejected/  (auto)
                              │
                       pending_for_approve
                              │
                              │ user via kb-wiki-review
                              ├─ approve ─▶ approved  (wiki/ 잔존)
                              └─ reject  ─▶ data/rejected/  (wiki 밖)
```

세 활성 상태와 한 terminal exit. `data/rejected/` 트리는 wiki/ 와 lint scope 모두에서 분리되어 audit 데이터로 보존된다.

## 6. Data Model

### 6.1 Frontmatter — 활성 wiki 페이지

기존 frontmatter에 `review_status` 한 줄 추가. 다른 field는 변경 없음.

```yaml
---
type: entity
review_status: not_processed   # not_processed | pending_for_approve | approved
created: "2026-05-19"
updated: "2026-05-19"
sources: [...]
tags: [...]
---
```

### 6.2 Frontmatter — rejected 파일 (`data/rejected/<orig path>`)

원본 frontmatter 보존 + 두 필드 추가:

```yaml
review_status: rejected
rejected_at: "2026-05-19T14:30:00+09:00"
rejected_by: user        # user | auto_ttl
```

`data/rejected/` 는 lint scope 밖이므로 schema 검증은 안 한다. 위 필드는 grep/패턴 분석 편의용 convention.

### 6.3 Body convention — `## User Feedback` 섹션

CLI가 review 액션마다 본문 끝의 단일 `## User Feedback` 섹션에 라인을 append. 여러 액션이 누적되면 라인 여러 줄.

```markdown
(...본문...)

## User Feedback

2026-05-19-Rejected: 소스 부족.
2026-05-20-Approved: 소스 보강됨. 재사용 가능한 지식.
```

라벨 종류:

- `YYYY-MM-DD-Approved: <user feedback>`
- `YYYY-MM-DD-Rejected: <user feedback>`
- `YYYY-MM-DD-Auto-rejected: <system reason>` (TTL sweep만)

빈 입력(사용자가 prompt에서 enter만)이면 라인 자체를 추가하지 않는다 — 빈 헤딩 노이즈 방지. 단 섹션은 한 번 생성된 후 유지.

`## User Feedback` 섹션이 이미 있으면 append, 없으면 본문 끝에 새로 생성.

**Reserved heading**: AI agent는 일반 콘텐츠에서 `## User Feedback` 헤더를 사용하지 않아야 한다 (이 섹션은 CLI 전용). 다른 의미로 피드백을 표현하려면 다른 heading 사용 (예: `## Feedback`, `## Reviewer Notes`). CLAUDE.md/템플릿에 명시.

## 7. CLI Surface

새 entry point: `kb-wiki-review`. Subcommand 6개.

| Subcommand | Transition | 호출자 | 비고 |
|---|---|---|---|
| `list [--status <s>]` | (read-only) | user | `<s>` 기본 `pending_for_approve`. `all` 가능 |
| `show <stem>` | (read-only) | user | frontmatter + body 전체 출력 |
| `promote <stem>` | not_processed → pending | daily-update agent | User Feedback 라인 추가 안 함 (시스템 액션) |
| `approve <stem> [--feedback <text>]` | pending → approved | user | --feedback 없으면 interactive prompt. `YYYY-MM-DD-Approved: <text>` append |
| `reject <stem> [--feedback <text>]` | pending → rejected | user | git mv to `data/rejected/`. `YYYY-MM-DD-Rejected: <text>` append. frontmatter에 rejected_at/by |
| `ttl-sweep [--days 7] [--dry-run]` | not_processed → rejected (auto) | cron | created가 N일 이전이면 rejected_by=auto_ttl로 자동 reject |

### 7.1 Interactive prompt 예시

```
$ kb-wiki-review approve AgencyAgents
Page: wiki/entities/agency-agents/2026-05/AgencyAgents.md
Status: pending_for_approve → approved
Feedback (empty to skip, Ctrl-D when done):
> 재사용 가능한 지식. 보존 가치 있음.
> ^D
✓ Approved. Feedback recorded.
```

### 7.2 Atomicity

한 액션 = (frontmatter write) + (body append) + 옵션(git mv).
CLI는 working tree만 변경. commit/push는 user 책임.
`reject` 의 `git mv` 는 git이 파일 이동을 추적하도록 필수 — `mv` 셸 명령으로 하지 않는다.

### 7.3 Error 응답

| 상황 | 응답 |
|---|---|
| `promote` 대상이 이미 pending/approved | exit 1, "promote only from not_processed" |
| `approve`/`reject` 대상이 not_processed | exit 1, "must be pending_for_approve; run promote first" |
| `approve`/`reject` 대상이 이미 approved/rejected | exit 1, 명시적 메시지 |
| `<stem>` 가 wiki/에 없음 | exit 1, "page not found" |
| `reject` 시 `data/rejected/<path>` 에 동명 충돌 | suffix `.rejected-<timestamp>.md` 부여 후 보존 |

## 8. Lint & Index Changes

### 8.1 `lint_wiki.py`

1. `REQUIRED_FM_FIELDS` 의 6 in-scope 타입에 `review_status` 추가.
2. `wiki/validators.py` 에 `REVIEW_STATUS_VALUES = {"not_processed", "pending_for_approve", "approved"}` enum 추가 + 검증 함수. 6 타입에 한해 적용.
3. **Orphan check 완화**: `review_status != "approved"` 페이지는 orphan warning 면제.
4. **Wikilink 존재 체크**: status 무시 (기존 그대로). approved → pending 도 OK. Reject 시 파일이 wiki/ 밖으로 나가면 자연스럽게 dead link로 잡힘 — 의도된 신호.
5. 다른 모든 검사 (stub, empty section, sources existence, raw immutability, frontmatter format)는 status 무관, 균일 적용.

### 8.2 `wiki/index.py` (build_index)

`review_status == "approved"` 페이지만 INDEX.md 항목 생성. 다른 status는 skip.

### 8.3 `wiki/checks.py` — sync 검사 완화

- `check_index_sync` (subject `_index.md`): on-disk pages 중 approved만 비교. pending이 disk에 있고 `_index.md` 미등재여도 warning 안 남.
- `check_global_index_sync`: approved-filtered 페이지와 INDEX.md 비교.

### 8.4 `data/rejected/` 는 lint 무관

`lint_wiki` 와 `lint_handoff` 모두 `data/rejected/` 를 스캔하지 않는다. 기존대로 `wiki/`, `raw/`, `handoffs/` 만 본다.

### 8.5 변경 파일 요약

| 파일 | 변경 |
|---|---|
| `src/kb_mcp/cli/lint_wiki.py` | REQUIRED_FM_FIELDS 6타입 업데이트, orphan 완화 |
| `src/kb_mcp/cli/wiki/validators.py` | REVIEW_STATUS_VALUES, `_validate_review_status` |
| `src/kb_mcp/cli/wiki/index.py` | build_index에 approved filter |
| `src/kb_mcp/cli/wiki/checks.py` | check_index_sync, check_global_index_sync에 status filter |
| `src/kb_mcp/cli/wiki_review.py` *(신규)* | 6 subcommand 진입점 |
| `pyproject.toml` | scripts entry: `kb-wiki-review` |
| `templates/wiki/{entity,concept,decision,improvement,checklist,question}.md` | `review_status: not_processed` 라인 추가 |
| `CLAUDE.md` (outer) | review_status field, edit 정책, INDEX 자동 동기화 안내 |
| `docs/workflows/wiki-approval-workflow.md` *(신규)* | operator manual (이 spec의 walkthrough 섹션 기반) |

## 9. Cron + Agent Contract

### 9.1 TTL sweep cron (deterministic)

새 wrapper: `scripts/cron/kb-wiki-ttl-sweep.sh` — 기존 daily report wrapper와 동일 패턴(flock, log).

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$KB_ROOT/.cron/logs"
LOCK_DIR="$KB_ROOT/.cron/locks"
mkdir -p "$LOG_DIR" "$LOCK_DIR"

if ! flock -n "$LOCK_DIR/wiki-ttl-sweep.lock" \
    bash -lc "cd '$KB_ROOT' && uv run kb-wiki-review ttl-sweep --days 7" \
    >> "$LOG_DIR/wiki-ttl-sweep.log" 2>&1; then
  echo "[$(date -Iseconds)] ERROR: ttl-sweep failed" >&2
  exit 1
fi
```

Cron 등록: `30 0 * * * /path/to/scripts/cron/kb-wiki-ttl-sweep.sh` (KST 00:30, 다른 dailies 전).

Sweep는 not_processed pages만 영향 — INDEX.md(approved-only)에 영향 없음 → lint를 부르지 않는다.

### 9.2 Daily-update agent contract (MVP는 문서만)

`docs/workflows/wiki-approval-workflow.md` 에 다음을 명시. 코드 변경 없음.

**Trigger**: 사용자가 Claude Code 세션에서 수동 invoke (MVP). 미래에 cron화 가능.

**Input**:
```bash
uv run kb-wiki-review list --status not_processed
```

**Decision rule** (LLM 판단, 규칙은 guideline):
- 소스가 명확하고 검증 가능한가
- 다른 wiki/handoff에서 참조될 가능성이 있는가
- 이벤트 dump가 아닌 *지식*인가 (시간이 지나도 가치 유지)

**Action**:
- promote: `uv run kb-wiki-review promote <stem>`
- leave: 아무것도 안 함 (다음 날 재고려, 7일째 자동 TTL)

**금지**: agent는 직접 reject 안 함. 사람만 reject. 이유: reject는 영구 wiki 밖 이동인데, LLM 오판은 사람 검토보다 위험이 큼. TTL은 deterministic 안전망.

## 10. End-to-end Walkthrough

### 10.1 Happy path: 새 entity 생성 → approve

```
Day 0 (writer AI session)
  wiki/entities/foo/2026-05/Foo.md  생성
    review_status: not_processed (템플릿 default)
  uv run kb-lint-wiki        → ✓
  INDEX.md                   → Foo 미포함 (approved 아님)

Day 1 (manual daily-update session)
  uv run kb-wiki-review list --status not_processed
    → Foo (1 day old)
  사용자/agent 판단 → promote
  uv run kb-wiki-review promote Foo
    review_status: not_processed → pending_for_approve

Day 2 (user review)
  uv run kb-wiki-review list
    → Foo (pending, 2 days)
  uv run kb-wiki-review show Foo
  uv run kb-wiki-review approve Foo
    > Feedback: 재사용 가능, 소스 검증됨.
    review_status: pending_for_approve → approved
    body 끝: ## User Feedback / 2026-05-21-Approved: 재사용 가능, 소스 검증됨.
  uv run kb-wiki-index       → INDEX.md에 Foo 등장
  uv run kb-lint-wiki        → subject _index.md sync 경고 (Foo 미등재)
  사용자가 entities/foo/_index.md 에 `- [[Foo]]` 라인 추가
  uv run kb-lint-wiki        → ✓
```

### 10.2 Reject path

```
Day 2 (user review)
  uv run kb-wiki-review reject Foo
    > Feedback: 144개 숫자가 출처 미상.
    git mv wiki/entities/foo/2026-05/Foo.md → data/rejected/entities/foo/2026-05/Foo.md
    frontmatter: review_status: rejected, rejected_at: <now>, rejected_by: user
    body 끝: ## User Feedback / 2026-05-21-Rejected: 144개 숫자가 출처 미상.
  uv run kb-lint-wiki
    → 만약 다른 approved 페이지가 [[Foo]] 를 링크하고 있었다면 dead link error
       (의도된 신호 — 사용자가 그 페이지 정리)
```

### 10.3 TTL auto-reject path

```
Day 0  not_processed 페이지 Bar 생성됨
Day 1~6  daily-update가 매일 보지만 매번 leave
Day 7 00:30 KST  ttl-sweep cron 발동
  git mv wiki/.../Bar.md → data/rejected/.../Bar.md
  frontmatter: rejected_by: auto_ttl, rejected_at: <now>
  body 끝: 2026-05-26-Auto-rejected: No promotion within 7d window.
```

### 10.4 Approved 페이지의 AI 수정

```
AI session
  approved 페이지 Foo.md 를 수정 (semantic 변화)
  AI는 edit과 함께 frontmatter review_status를 not_processed로 리셋
    (CLAUDE.md 가이드라인에 따른 self-discipline)
  INDEX.md 에서 Foo 자동 제거 (다음 kb-wiki-index 실행 시)
  다음 daily-update에서 다시 promote 후보로 재진입

만약 typo만 수정 (semantic 변화 없음)
  AI는 status 유지 (approved 그대로)
  INDEX.md 영향 없음

자동 감지는 안 함. drift 위험은 CLAUDE.md 가이드라인이 유일한 방어선.
```

## 11. Edge Cases

| 상황 | Intended behavior |
|---|---|
| AI 페이지 작성 시 `review_status` 누락 | Lint error (required field) — AI는 템플릿을 따라야 함 |
| `approve` 호출 대상이 이미 approved | CLI error: "already approved" — no-op |
| `promote` 대상이 이미 pending/approved | CLI error: "promote only from not_processed" |
| `reject` 대상이 wiki에 없음 (이미 rejected) | CLI error: "page not found in wiki/" |
| `data/rejected/<path>` 에 동명 파일 존재 | 새 파일에 `.rejected-<ISO timestamp>.md` suffix 부여 |
| TTL sweep 중 user가 같은 파일 편집 중 | git mv 가 working tree 충돌 감지 → CLI가 skip + warn, 다음 sweep 때 재시도 |
| Approved 페이지가 rejected 페이지를 wikilink | Lint dead-link error — user가 링크 제거 또는 출처 갱신 |
| User가 frontmatter `review_status` 직접 편집 | CLI 우회 — 자유지만 권장 안 함. Body User Feedback 라인 자동 생성 안 됨 |
| AI가 approved 페이지 semantic 편집 후 reset 잊음 | Drift 위험. CLAUDE.md 가이드만이 방어선 (의도된 trade-off) |
| ttl-sweep dry-run | 파일 변경 없이 sweep 대상 목록만 출력 |
| Subject `_index.md` sync — non-approved 페이지가 disk에 있음 | Warning 발생 안 함 (lint 완화) |
| Subject `_index.md` sync — approved인데 미등재 | Warning 발생 (기존 동작) |

## 12. Test Plan

### 12.1 Unit tests

- **Validators**:
  - `REVIEW_STATUS_VALUES` enum 검증 (valid / invalid value / missing field) on 각 in-scope type
  - summary type은 review_status 없어도 OK
- **Index filter**:
  - `build_index` 가 not_processed/pending 페이지 제외, approved만 포함
  - 빈 wiki, mixed status wiki 모두 검증
- **Sync 완화**:
  - `check_index_sync`: non-approved 페이지가 disk에 있고 `_index.md` 미등재 → warning 없음
  - approved 페이지가 disk에 있고 `_index.md` 미등재 → warning 발생 (기존 유지)

### 12.2 Integration tests (각 CLI subcommand)

| 테스트 | 검증 |
|---|---|
| `list` filter | --status 인자별 출력 차이, age 계산 정확성 |
| `show` | 정상 출력, 없는 stem → exit 1 |
| `promote` | not_processed → pending 전환, 이미 pending이면 에러 |
| `approve` --feedback | frontmatter status 변경, body `## User Feedback` 라인 append |
| `approve` 빈 feedback | status는 변경, body 변경 없음 |
| `approve` 기존 User Feedback 섹션 있음 | append 동작 |
| `reject` | git mv + frontmatter rejected_at/by + body 라인 + 동명 충돌 suffix |
| `ttl-sweep` | 8일 된 not_processed → rejected (auto_ttl), 6일 된 페이지는 skip |
| `ttl-sweep --dry-run` | 파일 변경 없이 대상 목록만 출력 |

### 12.3 End-to-end test

미니 wiki를 tmp 디렉토리에 만들어:
1. 6 in-scope 타입 각 1개씩 페이지 생성 (review_status: not_processed)
2. `promote` → 1개를 pending으로
3. `approve` → 1개를 approved로
4. `kb-wiki-index` 실행 → INDEX.md에 approved 1개만 등장 검증
5. `reject` → 다른 1개를 rejected로
6. data/rejected/ 트리에 파일 존재 + 원본 wiki/에 없음 검증
7. `kb-lint-wiki` → ✓ (rejected 페이지 wikilink 참조 없는 경우)

## 13. Migration

**일회성. CLI subcommand 만들지 않음** — 첫 실행 후 영구 dead code 방지 (Karpathy #2/#3).

배포 직후 한 번 실행:

```python
# Run once. Not part of permanent codebase.
import re
from pathlib import Path

TYPES = {"entity", "concept", "decision", "improvement", "checklist", "question"}

for p in Path("data/wiki").rglob("*.md"):
    text = p.read_text()
    if not text.startswith("---"):
        continue
    parts = text.split("---", 2)
    if len(parts) < 3:
        continue
    fm, body = parts[1], parts[2]
    if "review_status" in fm:
        continue
    m = re.search(r"^type:\s*(\w+)", fm, re.MULTILINE)
    if not m or m.group(1) not in TYPES:
        continue
    new_fm = fm.rstrip() + "\nreview_status: pending_for_approve\n"
    p.write_text(f"---{new_fm}---{body}")
    print(f"migrated {p}")
```

검증:
1. `uv run kb-lint-wiki` → 0 errors (모든 in-scope 페이지에 review_status 존재)
2. `uv run kb-wiki-review list` → 기존 in-scope 페이지 전체가 pending queue로 표시
3. `uv run kb-wiki-index` → INDEX.md가 빈 상태로 재생성 (모두 pending이라 approved 없음)

Migration 후 사용자가 `list` → `show` → `approve`/`reject` 로 기존 페이지를 하나씩 처리.

## 14. Setup Order (사용자 설치 직후)

1. `git pull && uv sync` (코드 + 6 템플릿 + CLAUDE.md 업데이트 수신)
2. Migration script 1회 실행 (§13)
3. `uv run kb-wiki-review list` → 기존 페이지 일괄 review
4. `uv run kb-wiki-index` → 비어있는 INDEX.md 또는 approve된 것만 포함
5. (옵션) `scripts/cron/kb-wiki-ttl-sweep.sh` 를 crontab에 등록 (새 페이지 작성 시작 시점에)
6. 기존 daily report cron들은 변경 불필요 (summary는 out of scope)

## 15. Out of Scope / Future

- **UI**: 이 CLI 데이터 모델 위에 web UI 또는 TUI를 추후 얹는다.
- **Cron-driven daily-update agent**: MVP에서 contract만, 사람이 invoke. 추후 LLM cron job으로 자동화.
- **`unreject` 명령**: 거의 안 쓸 것 같은 케이스. 수동 git mv + frontmatter 편집으로 처리.
- **Approved 페이지 edit semantic 자동 감지**: AI judgment + CLAUDE.md guideline로 충분히 시작. drift 측정 후 필요시 도입.
- **Per-page audit timeline (Approach B/C)**: 현재 `## User Feedback` 라인 + git history + data/rejected/ 트리로 충분. 본격 분석 필요할 때 도입.
- **검색 시스템**: 별도 spec 대상.

## 16. Risks

- **Daily-update agent의 promote 누락**: 사람이 직접 list 안 보면 not_processed 가 7일 후 자동 reject. 의도된 안전망이지만 *실제로 가치 있는 페이지가 누락될* 위험. 완화: TTL 기간 조정 가능 (`--days N`), 향후 list cron으로 사용자에게 알림 가능.
- **drift on approved pages**: AI semantic edit 후 status reset 안 하면 silent drift. 완화: CLAUDE.md 강력 명시, 첫 분기 사용자 spot-check 권장.
- **`data/rejected/` 누적**: 시간이 지나면 wiki rejection 데이터가 쌓임. 완화: 의도된 행동 (audit 자산). 너무 커지면 yearly archive (별도 작업).
