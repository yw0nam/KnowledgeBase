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
- pricing-exporter: `curl localhost:9091/healthz` → `models=N`
- 스키마 참조: `docs/db_informations/` 하위 문서

---

## 데이터 소스 전략 (중요)

| 지표 | 소스 |
|------|------|
| 모델별 토큰 / 실청구 / shadow | `message.data` (modelID, providerID, tokens.*, cost) |
| 세션 수 / root·subagent 구분 / 시간대 | `session` (parent_id, time_created) |
| 핫 파일 / compaction | `part` (type=patch, compaction) |
| 도구 에러율 | `part` (type=tool, state.status) |
| Todo 완료율 | `todo` (status) |
| Hermes 지표 전체 | `~/.hermes/state.db` (sessions 테이블) |

### 핵심: message.data.modelID가 정확한 이유

`session.model`은 subagent 세션에서 NULL이지만, **`message.data.modelID`에는 root/subagent 구분 없이 실제 모델명이 기록된다.**
subagent가 minimax, gpt-5.4-mini-fast, haiku를 사용했다면 각각의 modelID로 정확히 찍힌다.

### providerID별 비용 처리

| providerID | 실청구 | Shadow |
|------------|--------|--------|
| `anthropic` | 0 USD (Max 구독) | pricing-exporter 단가로 계산 |
| `openai` | 0 USD (구독) | pricing-exporter 단가로 계산 |
| `google` | 0 USD (구독) | pricing-exporter 단가로 계산 |
| `opencode-go` | `SUM(message.cost)` = 실청구 | pricing-exporter에 단가 있으면 shadow도 계산 |
| `vllm` | 0 USD (자체호스팅) | shadow 제외, 표에 명시 |

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

#### 2-A. OpenCode message DB — 모델별 토큰·비용 (Layer 1 핵심)

**KST 변환 필수**: `time_created/1000` + `'+9 hours'` 적용.

```sql
SELECT
  json_extract(m.data, '$.modelID')                        AS modelID,
  json_extract(m.data, '$.providerID')                     AS providerID,
  SUM(json_extract(m.data, '$.tokens.input'))              AS input_cache_miss,
  SUM(json_extract(m.data, '$.tokens.cache.read'))         AS cache_read,
  SUM(json_extract(m.data, '$.tokens.output'))             AS output,
  SUM(json_extract(m.data, '$.tokens.cache.write'))        AS cache_write,
  SUM(json_extract(m.data, '$.tokens.reasoning'))          AS reasoning,
  SUM(json_extract(m.data, '$.tokens.input')
    + json_extract(m.data, '$.tokens.cache.read'))         AS total_input,
  SUM(json_extract(m.data, '$.cost'))                      AS actual_cost
FROM message m
JOIN session s ON m.session_id = s.id
WHERE date(datetime(s.time_created/1000, 'unixepoch', '+9 hours')) = '${TARGET}'
  AND json_extract(m.data, '$.role') = 'assistant'
GROUP BY modelID, providerID
ORDER BY total_input DESC;
```

이 쿼리 하나로 root+subagent 전체 모델별 토큰과 실청구가 나온다.

> **`input_cache_miss`**: 캐시 미스 토큰만 (새로 읽힌 것). 실제 LLM 입력량은 `input_cache_miss + cache_read`.
> **캐시 히트율**: `cache_read / (input_cache_miss + cache_read) × 100`

#### 2-B. OpenCode SQLite — 세션 구조 / 작업 품질 / 행동 패턴

| 레이어 | 지표 | 소스 |
|--------|------|------|
| Layer 2 | Todo 완료율(completed/total), 도구별 에러율, compaction 발생 수 | `todo`, `part` |
| Layer 3 | 시간대별 세션 분포, root vs subagent 수 | `session.parent_id` |
| Layer 4 | 프로젝트별 세션 수, 핫 파일(수정 빈도 상위 10), 세션당 수정 파일 수 | `part.type=patch` |

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
shadow_cost = input_cache_miss × price_input
            + cache_read       × price_cache_read   # 캐시 히트는 단가가 훨씬 저렴
            + cache_write      × price_cache_write
            + output           × price_output
            + reasoning        × price_input        # reasoning은 input 단가 적용
```

> `input`과 `cache_read`는 단가가 다르므로 반드시 분리해서 계산한다.
> (예: claude-opus-4-7 input 5e-6 USD/tok vs cache_read 5e-7 USD/tok — 10배 차이)

#### 모델 처리 규칙

| providerID | 실청구 | Shadow |
|------------|--------|--------|
| `anthropic` | 0 USD (Max 구독) | pricing-exporter 단가로 계산 |
| `openai` | 0 USD (codex 구독) | pricing-exporter 단가로 계산 |
| `google` | 0 USD (Gemini 구독) | pricing-exporter 단가로 계산 |
| `opencode-go` | `SUM(message.cost)` | 실청구만 기재 |
| `vllm` | 0 USD (자체호스팅) | shadow 제외, 표에 명시 |

#### 기재 형식 (Layer 1 OpenCode)

```markdown
**OpenCode** _(토큰·비용: message DB 기준 / 세션 구조: session DB 기준)_
- 모델별 토큰:
  | 모델 | total_input | cache_miss | cache_read | output | cache_write | cache_hit |
  |------|------------:|-----------:|-----------:|-------:|------------:|----------:|
  | claude-opus-4-7 | N | N | N | N | N | N% |
  | gpt-5.5 | N | N | N | N | N | N% |
  | (실청구) glm-5/opencode-go | N | N | N | N | N | — |
  | (자체호스팅) chat_model/vllm | N | N | N | N | N | — |
- 실청구: N USD (opencode-go 모델 합산) / Shadow: N USD (anthropic+openai+google 계열)
- Shadow 상세:
  - claude-opus-4-7 — cache_miss N × 5e-6 + cache_read N × 5e-7 + output N × 2.5e-5 → X.XX USD
  - gpt-5.5 — ... → X.XX USD
- 단가 기준 (LiteLLM): pricing-exporter 실시간 조회값 사용
```

> `total_input = cache_miss + cache_read`. `cache_hit = cache_read / total_input × 100`

---

### Step 4: 파일 작성

템플릿: `templates/summary-daily_agent_usage.md`

각 레이어 안에서 **OpenCode → Hermes 순서**로 블록을 나란히 작성한다.
OpenCode Layer 1에는 **데이터 소스 출처** (message DB / session DB)를 명시한다.
데이터 없는 날: frontmatter만 채우고 본문은 `> 데이터 없음` 한 줄.

```markdown
## Layer 1: 비용·효율
**OpenCode** _(토큰·비용: message DB 기준 / 세션 구조: session DB 기준)_
- 모델별 토큰:
  | 모델 | input | output | cache_read | cache_write | 합계 | cache_hit |
  |------|------:|-------:|-----------:|------------:|-----:|----------:|
  | claude-opus-4-7 | N | N | N | N | N | N% |
  | claude-haiku-4-5 | N | N | N | N | N | N% |
  | minimax-m2.7 | N | N | N | N | N | N% |
- 실청구: N USD / Shadow: N USD
- Shadow 상세: ...

**Hermes**
- 총 토큰: N (input N / output N / cache_read N)
- 캐시 히트율: N%
- 실청구: N USD / Shadow: N USD (claude 계열만, 나머지 단가 불명확)
- 모델별 분포: model N세션, ...
```

#### Frontmatter 규칙

- `sources: []` — DB는 raw 파일이 아니므로 항상 빈 리스트
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
  - 소스: opencode.db (message/session/part/todo), hermes state.db, pricing-exporter (shadow 단가)
  - 출력: wiki/summaries/daily/YYYY-MM-DD_agent_usage.md
  - shadow 비용: X.XX USD (anthropic+openai+google 계열) / 실청구: X.XX USD (opencode-go 모델)
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

**session.model 사용 금지**
`session.model`은 subagent 세션에서 NULL. 모델 집계에 절대 사용하지 말 것.
반드시 `message.data.modelID`로 집계한다. root/subagent 구분 없이 실제 모델명이 정확히 기록된다.

**shadow 비용은 필수**
anthropic/openai/google은 구독이라 실청구 0이어도 반드시 shadow를 계산해서 기재.
실청구(opencode-go)와 shadow는 항상 분리해서 표기.

**달러 기호 금지**
비용 표기는 `17.73 USD` 형식. `$17.73` 사용 금지.

**git add는 명시적으로**
`git add .` 대신 파일 경로 직접 지정.

**pricing-exporter에 단가 없는 모델**
shadow 계산 제외하고 표에 명시적으로 `(단가불명)` 또는 `(자체호스팅)` 표기.
opencode-go 모델은 `message.cost` 합산이 실청구이므로 그대로 기재.
