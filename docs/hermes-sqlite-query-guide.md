# Hermes SQLite Query Guide — Daily Report Integration

Updated: 2026-05-08

## 1. Synopsis

- **Purpose**: Daily report 에이전트가 Hermes SQLite DB에서 도구 사용량·메시지·세션 통계를 조회하는 방법
- **I/O**: `~/.hermes/state.db` → 세션 요약, 도구 Top N, 토큰 집계

---

## 2. Core Logic

### DB 위치

| 경로 | 설명 | 우선순위 |
|------|------|----------|
| `~/.hermes/state.db` | **메인 DB** — 모든 세션·메시지 기록 | 필수 |
| `~/.hermes/profiles/*/state.db` | 프로파일별 독립 DB (멀티-에이전트) | 선택 |
| `~/.hermes/kanban.db` | 칸반 태스크 DB | 선택 |

> 프로파일 목록: `main-gateway`, `research-agent`, `execution-agent`, `structuring-agent`, `verification-agent`

### 핵심 테이블

**`sessions`** — 세션 단위 집계 (토큰·비용·도구 호출 수는 세션 종료 시 기록)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `source` | TEXT | `tui` \| `cli` \| `telegram` \| `slack` \| `cron` \| `api_server` |
| `model` | TEXT | 사용 모델명 |
| `started_at` | REAL | Unix epoch (초) |
| `ended_at` | REAL | NULL = 진행 중 |
| `message_count` | INTEGER | 세션 내 메시지 수 |
| `tool_call_count` | INTEGER | 도구 호출 횟수 |
| `input_tokens` | INTEGER | 입력 토큰 |
| `output_tokens` | INTEGER | 출력 토큰 |
| `cache_read_tokens` | INTEGER | 캐시 읽기 토큰 |
| `reasoning_tokens` | INTEGER | 추론 토큰 |
| `api_call_count` | INTEGER | API 호출 횟수 |
| `estimated_cost_usd` | REAL | 추정 비용 |
| `actual_cost_usd` | REAL | 실제 비용 |

**`messages`** — 메시지 단위 기록. 도구 호출 상세는 `tool_calls` JSON 컬럼에 저장

```json
// tool_calls 컬럼 구조 (role='assistant')
[{"type": "function", "function": {"name": "terminal", "arguments": "..."}}]
```

도구명 추출: `json_extract(value, '$.function.name')` + `json_each(tool_calls)`

### 제약

- 타임스탬프는 모두 **Unix epoch (REAL)**. `date(col, 'unixepoch')`으로 변환
- 프로파일 DB는 메인 `state.db`와 **별개** — 합산 시 개별 조회 필요
- 스키마 버전: `SELECT version FROM schema_version;` (현재: 11)

---

## 3. Usage

### 어제 전체 요약 (단일 행)

```bash
sqlite3 ~/.hermes/state.db "
SELECT date(started_at,'unixepoch') d,
       COUNT(DISTINCT id) sessions,
       SUM(message_count) msgs,
       SUM(tool_call_count) tool_calls,
       SUM(input_tokens) in_tok,
       SUM(output_tokens) out_tok,
       SUM(COALESCE(actual_cost_usd, estimated_cost_usd)) cost_usd
FROM sessions
WHERE d = date('now','-1 day')
GROUP BY d;"
```

### 소스·모델별 세션 분류

```sql
SELECT source, model,
       COUNT(DISTINCT id) sessions,
       SUM(message_count) messages,
       SUM(tool_call_count) tool_calls,
       SUM(input_tokens) input_tokens,
       SUM(output_tokens) output_tokens
FROM sessions
WHERE date(started_at, 'unixepoch') = date('now', '-1 day')
GROUP BY source, model
ORDER BY input_tokens DESC;
```

### 도구 사용 Top 10

```bash
sqlite3 ~/.hermes/state.db "
SELECT json_extract(value,'$.function.name') tool, COUNT(*) n
FROM messages, json_each(tool_calls)
WHERE tool_calls IS NOT NULL AND tool_calls != ''
  AND date(timestamp,'unixepoch') = date('now','-1 day')
GROUP BY tool ORDER BY n DESC LIMIT 10;"
```

### 소스별 도구 사용 분류

```sql
SELECT s.source,
       json_extract(value, '$.function.name') AS tool_name,
       COUNT(*) AS call_count
FROM messages m
JOIN sessions s ON m.session_id = s.id
JOIN json_each(m.tool_calls)
WHERE m.tool_calls IS NOT NULL AND m.tool_calls != ''
  AND date(m.timestamp, 'unixepoch') = date('now', '-1 day')
GROUP BY s.source, tool_name
ORDER BY call_count DESC;
```

---

## Appendix

### A. 추가 쿼리

**최근 7일 트렌드**
```sql
SELECT date(started_at, 'unixepoch') d,
       COUNT(DISTINCT id) sessions,
       SUM(input_tokens + output_tokens) total_tokens
FROM sessions
WHERE d >= date('now', '-7 days')
GROUP BY d ORDER BY d DESC;
```

**모델별 토큰 비율**
```sql
SELECT model,
       SUM(input_tokens + output_tokens) total_tokens,
       ROUND(100.0 * SUM(input_tokens + output_tokens)
             / SUM(SUM(input_tokens + output_tokens)) OVER (), 1) pct
FROM sessions
WHERE date(started_at, 'unixepoch') = date('now', '-1 day')
  AND model IS NOT NULL
GROUP BY model ORDER BY total_tokens DESC;
```

**진행 중 세션 제외**
```sql
WHERE ended_at IS NOT NULL
  AND date(started_at, 'unixepoch') = date('now', '-1 day')
```

### B. 프로파일 DB 통합 조회

```bash
#!/bin/bash
TARGET_DATE="${1:-$(date -d yesterday +%Y-%m-%d)}"
for db in ~/.hermes/state.db ~/.hermes/profiles/*/state.db; do
  [ -f "$db" ] || continue
  profile=$(basename $(dirname "$db"))
  sqlite3 "$db" "
    SELECT '$profile' profile, source, model,
           COUNT(DISTINCT id) sessions,
           SUM(message_count) messages,
           SUM(tool_call_count) tool_calls,
           SUM(input_tokens) input_tokens
    FROM sessions
    WHERE date(started_at,'unixepoch')='$TARGET_DATE'
    GROUP BY source, model;"
done
```

### C. end_reason 값 목록

| 값 | 설명 |
|----|------|
| `cli_close` | CLI 세션 종료 |
| `tui_close` / `tui_shutdown` | TUI 세션 종료 |
| `cron_complete` | 크론 작업 완료 |
| `session_reset` | 세션 리셋 |
| `compression` | 컨텍스트 압축 |
| NULL | 비정상 종료 또는 진행 중 |

### D. PatchNote

2026-05-08: 최초 작성. 실제 DB 조회 기반으로 스키마·쿼리 검증 완료.
