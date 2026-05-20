# Cron Scope Artifact — Design Spec

**Date**: 2026-05-20
**Status**: Draft (brainstorming complete, awaiting user review)
**Supersedes**: `2026-05-20-kb-ingest-cli-design.md`

## 1. Problem

`kb-memory-daily`, `kb-memory-weekly`, `kb-memory-monthly`, `kb-wiki-promote` cron agent 들은 "오늘 무엇을 후보로 삼을지" 를 결정할 때 `data/raw/`, `data/handoffs/`, `data/wiki/` 트리를 광범위하게 스캔해야 한다. 결과:

- Token/latency 비용 큼 (cron 마다 전체 트리 재독)
- 결정 비결정적 — 같은 시점이라도 agent 가 어디까지 보느냐에 따라 결과 달라짐
- 사람이 "오늘 시스템이 무얼 보고 있는지" 알려면 별도로 dashboard 띄우거나 트리 스캔

`kb-wiki-promote` 만 `kb-wiki-review list --status not_processed` 로 focused 입력을 받음. 다른 셋은 막막한 prompt 만 받는다.

## 2. Goals

1. 각 cron agent 가 *자기 섹션만 읽고* 후보 결정 가능한 단일 markdown artifact 생성.
2. 매일 한 번 결정적으로 재생성 — 같은 입력 → 같은 출력.
3. 사람도 `cat data/CRON_SCOPE.md` 로 동일 view 확인 (관측성).
4. 기존 cron/lint/wiki-review 인프라에 surgical 변경만 — 새 Python 모듈 0.

## 3. Non-goals

- 실시간 view (Web dashboard 역할). 일 1회 스냅샷이면 충분.
- 외부 시스템 (GitHub, Linear) 연결.
- 4-bucket citation 의미 모델 (이전 ingest spec) — 본 spec 은 agent 입력 artifact 에 집중.
- Multi-day diff/history. git 이 그 역할.
- Web/API 노출 — 향후 별도 spec.

## 4. Scope

### 생성 측 (regen)
- 입력: `data/raw/`, `data/handoffs/`, `data/wiki/`, `data/rejected/`, `git log -- data/`
- 출력: `data/CRON_SCOPE.md` (atomic write via tmp + mv)
- 트리거: 매일 00:45 KST (TTL sweep 직후)

### 소비 측 (consumers)
- `kb-memory-daily.sh` (03:30)
- `kb-wiki-promote.sh` (04:00)
- `kb-memory-weekly.sh` (Sunday 05:00)
- `kb-memory-monthly.sh` (1st 06:00)

각 consumer 의 첫 단계: sentinel check → fail loud or proceed.

## 5. File Schema

```markdown
# Cron Scope — YYYY-MM-DD (HH:MM KST)

## For daily-memory
### New since YYYY-MM-DD (git diff)
- handoffs/...
- raw/...

### Uncited handoffs older than 3 days (N)
- YYYY-MM-DD  handoffs/...

## For promote
### not_processed pages (N)
- <stem> (Nd)

### Aging toward TTL (≥5d) (N)
- <stem> (Nd)

## For weekly
### Pages added/modified this week (N)
- <stem>

### Top subjects by activity
- <subject>: N edits

## For monthly
### This month
- N pages (X approved / Y pending / Z not_processed)
- types: improvement A, entity B, concept C, decision D

### Stale approved (no edit in 30d) (N)
- <stem>

## System health
- Last memory-daily:  YYYY-MM-DD HH:MM ✓|✗
- Last promote:        YYYY-MM-DD ✓|✗
- Last ttl-sweep:      YYYY-MM-DD HH:MM ✓|✗
- Last regen:          YYYY-MM-DD HH:MM ✓
- Lint (last run):     PASSED|FAILED at YYYY-MM-DD
```

**Constraints**:
- 첫 줄은 정확히 `# Cron Scope — YYYY-MM-DD (HH:MM KST)` (sentinel parser 가 의존).
- 전체 **200줄 hard limit**. 초과 시 truncate 자동 발동 (§10 참조).
- 모든 list 정렬: 날짜 desc → 경로 asc.
- "Since" 기준일: 직전 `data/CRON_SCOPE.md` 의 헤더에서 추출, 없으면 yesterday (KST).

## 6. Regen Script

`scripts/cron/kb-regen-scope.sh`, bash ~100줄.

핵심 단계:
1. `set -euo pipefail`, KST timezone fix
2. `flock -n` lock (재생성 동시 실행 차단)
3. tmp file 작성 (`mktemp`)
4. 각 섹션 함수 호출 (`render_daily`, `render_promote`, `render_weekly`, `render_monthly`, `render_health`)
5. 200줄 초과 시 truncate 로직 발동
6. `mv $tmp data/CRON_SCOPE.md` (atomic)

각 render 함수는 stdout 으로 markdown 출력. 데이터 수집 도구:
- `find data/raw data/handoffs -newer ...` → "new since"
- `grep -rh '^  - handoffs/' data/wiki/ data/rejected/` → cited paths
- `uv run kb-wiki-review list --status not_processed` → promote 후보
- `git -C data log --since=... --name-only` → 활동량
- `data/.cron/logs/*.log` 의 마지막 줄 또는 mtime → health

신규 외부 의존성 0.

## 7. Sentinel Helper

`scripts/cron/_scope_sentinel.sh`, bash ~15줄.

```bash
#!/usr/bin/env bash
set -euo pipefail
SCOPE="${KB_ROOT}/data/CRON_SCOPE.md"
TODAY="$(TZ=Asia/Seoul date +%F)"
if [[ ! -f "$SCOPE" ]]; then
  echo "ERROR: scope missing at $SCOPE" >&2
  exit 1
fi
HEADER="$(head -1 "$SCOPE")"
if [[ "$HEADER" != *"$TODAY"* ]]; then
  echo "ERROR: scope stale; header=$HEADER expected $TODAY" >&2
  exit 1
fi
```

각 consumer 가 `source _scope_sentinel.sh || exit 1` 로 첫 단계에서 호출. Fail loud → opencode 호출 비용 절감.

Sentinel 실패 시 handoff 작성: consumer 가 trap 으로 `data/handoffs/YYYY/MM/scope-fail/` 에 한 줄짜리 노트 남김.

## 8. Cron Schedule

| 시각 | Job | 변경 |
|---|---|---|
| 00:30 | `kb-wiki-ttl-sweep` | 그대로 |
| **00:45** | **`kb-regen-scope` (신규)** | 신규 |
| 03:30 | `kb-memory-daily` | sentinel + prompt 갱신 |
| 04:00 | `kb-wiki-promote` | sentinel + prompt 갱신 |
| Sun 05:00 | `kb-memory-weekly` | sentinel + prompt 갱신 |
| 1st 06:00 | `kb-memory-monthly` | sentinel + prompt 갱신 |

## 9. Prompt Updates

각 cron wrapper 의 opencode prompt 앞부분에 추가:

```
"Read data/CRON_SCOPE.md first. Your candidates are in section
'For <agent-name>'. Do NOT scan data/wiki, data/raw, or data/handoffs
exhaustively unless your section explicitly tells you to."
```

CRON_SCOPE.md 가 모든 agent 의 **권위적 입력**. `kb-wiki-review list` 는 사람 디버깅용으로 계속 제공되지만, agent prompt 에는 "scope 만 본다" 를 명시 — 진실 경로 단일화.

## 10. Edge Cases

- **`data/.git` 없음**: regen 의 git 의존 부분 skip, "git unavailable" 노트.
- **First run (어제 데이터 없음)**: "new since" 섹션 비움 + "(no prior scope)" 표기.
- **200줄 초과**: 각 섹션 상위 20 + `... and N more` 추가. truncate 트리거 시 system health 에 경고 한 줄.
- **regen 자체가 lock 충돌**: `flock -n` 실패 → exit 1, 다음날 sentinel 이 fail loud.
- **DST/timezone**: 모두 `TZ=Asia/Seoul` 고정.
- **사람의 직접 편집**: scope 파일은 generated artifact. 사람이 직접 편집해도 다음 regen 에서 덮어쓰임. 의도된 동작.

## 11. Tests

총 **4개** (bash 테스트, pytest 외부):

1. `kb-regen-scope.sh` 가 빈 KB 에서 모든 섹션 헤더와 sentinel 라인 생성
2. `kb-regen-scope.sh` 가 200줄 초과 시 truncate 적용
3. `_scope_sentinel.sh` exit 0 on today's header
4. `_scope_sentinel.sh` exit 1 on stale/missing

스냅샷 형식 검증은 정규식 기반 (라인 수, 헤더 패턴).

## 12. Escalation Triggers

다음 시점에 본 spec 재검토:

1. regen 스크립트 실행 시간 P95 > 30초 (현재 예상 < 5초)
2. scope 파일 200줄 truncate 가 빈번 (>주 1회)
3. agent 가 자기 섹션 밖 트리 스캔을 prompt 무시하고 계속 함 (관측 시)
4. Web/API 노출 요구 발생

## Appendix

### A. 이전 `kb-ingest` spec 과의 관계

`2026-05-20-kb-ingest-cli-design.md` 는 사람용 CLI 로 설계됨. 본 spec 은 agent 입력 artifact 로 방향 전환. 두 design 의 공통 핵심 (citation map: source path → citing wiki pages) 은 본 spec 의 regen 스크립트 안에 흡수됨 — 별도 CLI 명령 없이 markdown 섹션으로 직접 렌더링.

### B. 왜 JSON 안 쓰는가

세 청중 (cron agent, 사람, future automation) 모두에 단일 포맷이 필요하면 markdown 이 우위. JSON 은 agent context 효율은 좋지만 사람이 직접 읽기 어렵고, 본 spec 의 3대 목표 (efficiency, determinism, observability) 중 observability 가 깨짐. 향후 자동화가 진짜로 JSON 을 요구하면 `data/CRON_SCOPE.json` 추가 (양쪽 단일 regen 호출에서 동시 생성).

### C. 왜 Web dashboard 와 별도인가

Web dashboard 는 실시간/인터랙티브. CRON_SCOPE 는 *어제 자정 시점의 결정 기준* 으로 동결된 스냅샷. 다음날 cron 결정의 재현성을 위해 이 동결이 핵심. dashboard 는 사람용 라이브 뷰, scope 는 agent 용 결정 입력 — 역할 분리.

### D. PatchNote

- 2026-05-20: Initial spec. Supersedes kb-ingest-cli-design.
