---
name: usage_daily-report
description: Agent usage daily report. 매일 새벽 3~4시에 전날 하루치 OpenCode + Hermes 사용량을 분석하고 data/wiki/summaries/daily/에 리포트를 작성한다.
license: MIT
---

# KB Daily Report Skill

매일 새벽 3~4시, 전날(KST 기준) 하루치 agent usage report를 작성하는 워크플로우.

## 전제 조건

작업 전 아래를 확인한다. 하나라도 실패하면 `data/wiki/summaries/daily/`에 오류 내용을 기재한 report를 작성하고 종료.

- OpenCode DB: `~/.local/share/opencode/opencode.db`
- Hermes DB: `~/.hermes/state.db`
- Prometheus: `curl -s http://localhost:9090/-/healthy` → `Prometheus Server is Healthy.`
- pricing-exporter: `curl localhost:9091/healthz` → `models=N`
- 스키마 참조: `docs/db_informations/` 하위 4개 문서

---

## 데이터 소스 전략 (중요)

**두 소스를 조합해서 사용한다. 단독 사용 금지.**

| 지표 | 소스 | 이유 |
|------|------|------|
| 세션 수 / root·subagent 구분 | SQLite `session.parent_id` | DB가 정확. Prometheus는 is_subagent 레이블만 있음 |
| 모델별 토큰 / shadow 비용 | **Prometheus** `opencode_token_usage_tokens_total` | SQLite의 subagent `session.model`은 전부 NULL. Prometheus OTel에만 실제 모델명 기록됨 |
| 실청구 비용 | **Prometheus** `opencode_cost_usage_USD_total` | 모델별 실청구 집계 가능 |
| 핫 파일 / todo / compaction | SQLite `part`, `todo` | Prometheus에 없는 정보 |
| Hermes 지표 전체 | SQLite `~/.hermes/state.db` | Hermes는 OTel 미연동, DB가 유일 소스 |

### 왜 SQLite model이 NULL인가

OpenCode는 subagent 세션을 spawn할 때 `session.model` 컬럼에 값을 기록하지 않는다 (upstream 버그).
OTLP emit 시에는 model attribute를 포함하므로 Prometheus에만 실제 모델명이 남는다.
→ **모델별 토큰/비용은 반드시 Prometheus에서 가져온다.**

---

## 워크플로우

### Step 1: 대상일 확정

1. 유저가 날짜를 명시한 경우, 해당 날짜 사용.
2. 명시하지 않은 경우, 대상일 = **어제 (KST)**

```bash
TARGET=$(date -d "yesterday" +%Y-%m-%d)   # Linux
# TARGET=$(date -v-1d +%Y-%m-%d)          # macOS
```

출력 파일명: `${TARGET}_agent_usage.md`

---

### Step 2: 지표 수집

스키마는 `docs/db_informations/` 문서를 읽고 쿼리를 직접 작성한다.

#### 2-A. SQLite 수집 지표 (세션 구조 / 작업 품질 / 행동 패턴)

**KST 변환 필수**: `time_created/1000` + `'+9 hours'` 적용.

| 레이어 | 지표 | 소스 |
|--------|------|------|
| Layer 2 | Todo 완료율(completed/total), 도구별 에러율, compaction 발생 수 | SQLite |
| Layer 3 | 시간대별 세션 분포, root vs subagent 수 | SQLite `session.parent_id` |
| Layer 4 | 프로젝트별 세션 수, 핫 파일(수정 빈도 상위 10), 세션당 수정 파일 수 | SQLite `patch.files` |

#### 2-B. Prometheus 수집 지표 (모델별 토큰 / 비용)

**KST 기준 하루 구간**: `start=YYYY-MM-DDT00:00:00+09:00`, `end=YYYY-MM-DDT23:59:59+09:00`

```bash
# 모델별 토큰 (type: input/output/cacheRead/cacheCreation/reasoning)
curl -sG 'http://localhost:9090/api/v1/query_range' \
  --data-urlencode 'query=sum by (model, type) (increase(opencode_token_usage_tokens_total{service_name="opencode"}[1d]))' \
  --data-urlencode "start=${TARGET}T00:00:00+09:00" \
  --data-urlencode "end=${TARGET}T23:59:59+09:00" \
  --data-urlencode 'step=86400'

# 모델별 실청구 비용
curl -sG 'http://localhost:9090/api/v1/query_range' \
  --data-urlencode 'query=sum by (model) (increase(opencode_cost_usage_USD_total{service_name="opencode"}[1d]))' \
  --data-urlencode "start=${TARGET}T00:00:00+09:00" \
  --data-urlencode "end=${TARGET}T23:59:59+09:00" \
  --data-urlencode 'step=86400'
```

> **주의**: Prometheus `increase()` 는 counter reset 시 오차가 생길 수 있다. 세션 수 등 정확도가 중요한 지표는 SQLite를 우선한다.

#### 2-C. Hermes 수집 지표 (SQLite 전용)

Hermes는 OTel 미연동. `~/.hermes/state.db` 단독 사용.
**KST 변환**: `started_at` (초 단위 float) + `'+9 hours'` 적용.
**root 세션만 집계**: `WHERE parent_session_id IS NULL` (중복 방지)

| 레이어 | 지표 |
|--------|------|
| Layer 1 | 모델별 세션 수 + 토큰(input/output/cache_read/cache_write/reasoning), 실청구 비용 |
| Layer 2 | end_reason 분포, 좀비 세션 수(ended_at IS NULL) |
| Layer 3 | source별 분포, 평균 세션 시간(초) |
| Layer 4 | root vs subagent 수, 모델별 세션 수 |

---

### Step 3: Shadow 비용 계산

#### pricing-exporter 단가 조회

```bash
curl -s localhost:9091/metrics | grep 'model_pricing_usd_per_token' | grep -v '#'
```

#### 계산 공식

```
shadow_cost = input × price_input
            + output × price_output
            + cache_read × price_cache_read
            + cache_write × price_cache_write
            + reasoning × price_input   # reasoning은 input 단가 적용
```

#### 모델 처리 규칙

| 상황 | 처리 |
|------|------|
| Prometheus `model` 레이블 있음 | 해당 모델 단가로 shadow 계산 |
| pricing-exporter에 단가 없는 모델 (Qwen, minimax 등) | shadow 계산 제외, 실청구만 기재 |
| OpenCode SQLite `model = NULL` | **Prometheus 데이터로 대체** (SQLite NULL은 무시) |
| Hermes `actual_cost_usd` | 실청구 비용으로 별도 기재 |

#### 기재 형식 (Layer 1 OpenCode)

```markdown
- 실청구: N USD / Shadow: N USD (claude+gpt 계열, 단가 불명확 모델 제외)
- Shadow 상세:
  - claude-opus-4-7 — input N / output N / cache_read N / cache_write N → X.XX USD
  - claude-haiku-4-5 — ... → X.XX USD
  - (단가 불명확: minimax-m2.7 N tok — shadow 제외)
- 단가 기준 (LiteLLM): 모델별 상이, pricing-exporter 실시간 조회값 사용
```

---

### Step 4: 파일 작성

템플릿: `templates/summary-daily_agent_usage.md`

각 레이어 안에서 **OpenCode → Hermes 순서**로 블록을 나란히 작성한다.
OpenCode Layer 1에는 **데이터 소스 출처** (Prometheus/SQLite)를 명시한다.
데이터 없는 날: frontmatter만 채우고 본문은 `> 데이터 없음` 한 줄.

```markdown
## Layer 1: 비용·효율
**OpenCode** _(토큰·비용: Prometheus OTel 기준 / 세션 구조: SQLite 기준)_
- 모델별 토큰:
  | 모델 | input | output | cache_read | cache_write | 합계 | cache_hit |
  |------|------:|-------:|-----------:|------------:|-----:|----------:|
  | claude-opus-4-7 | N | N | N | N | N | N% |
  | claude-haiku-4-5 | N | N | N | N | N | N% |
  | (단가불명) minimax-m2.7 | N | N | N | N | N | N% |
- 실청구: N USD / Shadow: N USD
- Shadow 상세: ...

**Hermes**
- 총 토큰: N (input N / output N / cache_read N)
- 캐시 히트율: N%
- 실청구: N USD / Shadow: N USD (claude 계열만, 나머지 단가 불명확)
- 모델별 분포: model N세션, ...
```

#### Frontmatter 규칙

- `sources: []` — DB/Prometheus는 raw 파일이 아니므로 항상 빈 리스트
- `type: summary` — 따옴표 없이
- 비용 표기: `17.73 USD` 형식, 달러 기호(`$`) 사용 금지

---

### Step 5: Lint

```bash
uv run kb-lint-wiki
```

**errors 0** 확인. 자주 나오는 에러:

| 에러 | 원인 | 수정 |
|------|------|------|
| `source file not found` | sources에 DB 경로 기재 | `sources: []`로 변경 |
| `type value is quoted` | `type: "summary"` | `type: summary`로 변경 |

warnings (orphan, stub)은 daily report 특성상 정상 — 무시.

---

### Step 6: log.md 업데이트

`data/log.md`에 append:

```markdown
## YYYY-MM-DD

- **fill**: YYYY-MM-DD daily report 생성
  - 소스: opencode.db (세션구조), Prometheus (모델별 토큰·비용), hermes state.db
  - 출력: wiki/summaries/daily/YYYY-MM-DD_agent_usage.md
  - shadow 비용: X.XX USD (claude+gpt 계열 기준)
- **lint**: kb-lint-wiki PASSED (errors 0)
```

---

### Step 7: git commit

```bash
cd data/
git add log.md wiki/summaries/daily/${TARGET}_agent_usage.md
git commit -m "report(daily_usage): daily agent usage report ${TARGET}

- kb-lint-wiki PASSED"
```

`git add .` 금지 — 이번 작업과 무관한 변경이 딸려올 수 있음.

---

## 주의사항

**SQLite model=NULL 문제**
OpenCode subagent 세션의 `session.model`은 전부 NULL. 이를 claude-opus-4-7로 가정하면 shadow 비용이 과대 계산된다.
반드시 Prometheus `opencode_token_usage_tokens_total{model="..."}` 로 실제 모델별 토큰을 가져온다.

**shadow 비용은 필수**
구독이라 실청구가 0이어도 반드시 계산해서 기재. 실청구 비용과 shadow 비용은 항상 분리.

**달러 기호 금지**
비용 표기는 `17.73 USD` 형식. `$17.73` 사용 금지.

**git add는 명시적으로**
`git add .` 대신 파일 경로 직접 지정.

**Prometheus 데이터 없을 때**
Prometheus가 다운되었거나 해당 날짜 데이터가 없으면 SQLite 기반으로 fallback하되,
Layer 1 상단에 `> ⚠️ Prometheus 데이터 없음 — 모델별 토큰은 SQLite 기반 근사치 (subagent model=NULL → claude-opus-4-7 가정)` 경고를 명시한다.
