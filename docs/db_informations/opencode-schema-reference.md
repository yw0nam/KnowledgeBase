# OpenCode SQLite Schema Reference

Updated: 2026-05-11

## 1. Synopsis

- **Purpose**: OpenCode DB 스키마 레퍼런스. 에이전트가 쿼리 작성 전 참조하는 원천 문서.
- **DB**: `~/.local/share/opencode/opencode.db` (SQLite 3.51.2, Drizzle ORM, WAL 모드)

---

## 2. 테이블 관계도

```
project ──< session ──< part
                  └──< message ──< part
                  └──< todo
                  └──< session_share
```

- `project.id` → `session.project_id`
- `session.id` → `part.session_id`, `message.session_id`, `todo.session_id`
- `message.id` → `part.message_id`

---

## 3. 테이블 스키마

### project

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | TEXT PK | 프로젝트 식별자 |
| `worktree` | TEXT | 작업 디렉토리 경로 |
| `name` | TEXT | 프로젝트 이름 (NULL 가능) |
| `time_created` | INTEGER | Unix epoch 밀리초 |
| `time_updated` | INTEGER | Unix epoch 밀리초 |

### session

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | TEXT PK | 세션 식별자 (`ses_...`) |
| `project_id` | TEXT FK | → `project.id` |
| `parent_id` | TEXT | NULL = root 세션, 값 있음 = subagent 세션 |
| `title` | TEXT | 세션 제목 |
| `model` | TEXT (JSON) | root 세션만 기록. **subagent 세션은 NULL** (upstream 미기록) |
| `agent` | TEXT | 에이전트 이름 (예: `Sisyphus - Ultraworker`) |
| `directory` | TEXT | 작업 디렉토리 경로 |
| `time_created` | INTEGER | Unix epoch 밀리초 |
| `time_updated` | INTEGER | Unix epoch 밀리초 |

> ⚠️ **`session.model`은 모델 집계에 사용하지 말 것.** subagent 세션은 NULL이므로 불완전하다.
> 실제 모델명은 `message.data.modelID`에 root/subagent 구분 없이 정확히 기록된다.

### part

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | TEXT PK | 파트 식별자 (`prt_...`) |
| `message_id` | TEXT FK | → `message.id` |
| `session_id` | TEXT FK | → `session.id` |
| `time_created` | INTEGER | Unix epoch 밀리초 |
| `data` | TEXT (JSON) | `data.type`으로 분기 (아래 참조) |

**`data.type` 값 목록**

| type | 비율 | 설명 |
|------|------|------|
| `tool` | 34% | 도구 호출 1건 |
| `step-start` | 19% | API 호출 시작 |
| `step-finish` | 19% | API 호출 완료 — 토큰·비용의 유일한 소스 |
| `reasoning` | 14% | Extended thinking 내용 |
| `text` | 13% | 텍스트 응답 |
| `patch` | 2% | 파일 변경 스냅샷 |
| `file` | <1% | 첨부 파일 |
| `compaction` | <1% | 컨텍스트 압축 발생 |

### todo

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `session_id` | TEXT FK | → `session.id` |
| `content` | TEXT | 할 일 내용 |
| `status` | TEXT | `pending` \| `in_progress` \| `completed` \| `cancelled` |
| `priority` | TEXT | `high` \| `medium` \| `low` |
| `position` | INTEGER | 순서 (PK 구성요소) |
| `time_created` | INTEGER | Unix epoch 밀리초 |

---

## 4. part.data JSON 구조 (타입별)

### step-finish
```json
{
  "type": "step-finish",
  "reason": "tool-calls",
  "snapshot": "a2ff2a1b...",
  "tokens": {
    "total": 42537,
    "input": 1592,
    "output": 113,
    "reasoning": 0,
    "cache": { "write": 0, "read": 40832 }
  },
  "cost": 0
}
```
> `total = input + cache.read + output`
> **`input` = 캐시 미스 토큰만** (새로 읽힌 것). `cache.read` = 캐시 히트 토큰.
> 실제 LLM 입력량 = `input + cache.read`. 캐시 히트율 = `cache.read / (input + cache.read)`
> 구독 모델(anthropic/openai/google)은 `cost = 0`. shadow 비용은 pricing-exporter 단가로 별도 계산.

### tool
```json
{
  "type": "tool",
  "tool": "bash",
  "callID": "toolu_...",
  "state": {
    "status": "completed",
    "input": { "command": "ls -la" },
    "metadata": { "output": "..." }
  }
}
```
> `state.status`: `completed` | `error` | `running` | `pending`

### patch
```json
{
  "type": "patch",
  "hash": "a2ff2a1b...",
  "files": ["/absolute/path/to/file.py"]
}
```

### reasoning
```json
{
  "type": "reasoning",
  "thinking": "..."
}
```

### compaction
```json
{
  "type": "compaction"
}
```
> 세션이 너무 길어져 컨텍스트 압축이 발생했음을 나타냄.

---

## Appendix

### A. 공통 제약

- 모든 `time_*` 컬럼은 **밀리초 epoch** → `datetime(col/1000,'unixepoch')`
- `session.model`은 root 세션만 기록, subagent는 NULL → **모델 집계에 사용 금지**
- **모델별 토큰·비용은 `message` 테이블에서 집계** (아래 §B 참조)
- `patch.files`는 JSON 배열 → `json_each(json_extract(data,'$.files'))`로 펼치기

### B. message 테이블 — 토큰·비용 집계 (핵심)

`message.data` (JSON)에 root/subagent 구분 없이 실제 모델명과 토큰이 기록된다.

```sql
-- 날짜별 모델별 토큰·비용 집계 (KST 기준)
SELECT
  json_extract(m.data, '$.modelID')                        AS modelID,
  json_extract(m.data, '$.providerID')                     AS providerID,
  SUM(json_extract(m.data, '$.tokens.input'))              AS input_cache_miss,   -- 캐시 미스 토큰만
  SUM(json_extract(m.data, '$.tokens.cache.read'))         AS cache_read,         -- 캐시 히트 토큰
  SUM(json_extract(m.data, '$.tokens.output'))             AS output,
  SUM(json_extract(m.data, '$.tokens.cache.write'))        AS cache_write,
  SUM(json_extract(m.data, '$.tokens.reasoning'))          AS reasoning,
  SUM(json_extract(m.data, '$.tokens.input')
    + json_extract(m.data, '$.tokens.cache.read'))         AS total_input,        -- 실제 LLM 입력량
  SUM(json_extract(m.data, '$.cost'))                      AS actual_cost
FROM message m
JOIN session s ON m.session_id = s.id
WHERE date(datetime(s.time_created/1000, 'unixepoch', '+9 hours')) = 'YYYY-MM-DD'
  AND json_extract(m.data, '$.role') = 'assistant'
GROUP BY modelID, providerID
ORDER BY total_input DESC;
```

> **캐시 히트율** = `cache_read / (input_cache_miss + cache_read) × 100`
> **Shadow 계산 시**: `input_cache_miss × p_input + cache_read × p_cache_read` (단가가 다르므로 반드시 분리)

**providerID별 비용 처리 규칙:**

| providerID | 실청구 | Shadow |
|------------|--------|--------|
| `anthropic` | 0 USD (Max 구독) | pricing-exporter 단가로 계산 |
| `openai` | 0 USD (구독) | pricing-exporter 단가로 계산 |
| `opencode-go` | `message.cost` 합산 = 실청구 | pricing-exporter에 단가 없으면 shadow 제외 |
| `google` | 0 USD (구독) | pricing-exporter 단가로 계산 |
| `vllm` | 0 USD (자체호스팅) | shadow 제외 |

### B. 인덱스 (성능 참고)

```
part_session_idx          ON part(session_id)
part_message_id_id_idx    ON part(message_id, id)
session_project_idx       ON session(project_id)
session_parent_idx        ON session(parent_id)
todo_session_idx          ON todo(session_id)
```

### C. 관련 문서

- `opencode-monitoring-guide.md` — 무엇을 왜 모니터링할지 지표 정의
