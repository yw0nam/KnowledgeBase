# Hermes SQLite Schema Reference

Updated: 2026-05-11

## 1. Synopsis

- **Purpose**: Hermes DB 스키마 레퍼런스. 에이전트가 쿼리 작성 전 참조하는 원천 문서.
- **DB**: `~/.hermes/state.db` (SQLite, WAL 모드, FTS5, schema v11)

---

## 2. DB 위치

| 경로 | 설명 |
|------|------|
| `~/.hermes/state.db` | **메인 DB** — 모든 세션·메시지 기록 |
| `~/.hermes/profiles/*/state.db` | 프로파일별 독립 DB (멀티-에이전트) |
| `~/.hermes/kanban.db` | 칸반 태스크 DB |

**프로파일 목록**: `main-gateway`, `research-agent`, `execution-agent`, `structuring-agent`, `verification-agent`

> 프로파일 DB는 메인 DB와 **완전히 별개**. 합산 시 개별 조회 후 UNION 필요.

---

## 3. 테이블 관계도

```
sessions ──< messages
         └──< messages_fts        (FTS5 전문 검색)
         └──< messages_fts_trigram (CJK/부분 문자열 검색)
state_meta                         (키-값 메타데이터)
schema_version                     (마이그레이션 버전)
```

- `sessions.id` → `messages.session_id`
- `sessions.parent_session_id` → `sessions.id` (self-referential, context compression 분기)

---

## 4. 테이블 스키마

### sessions

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | TEXT PK | 세션 식별자 (`YYYYMMDD_HHMMSS_hex`) |
| `source` | TEXT | `cli` \| `tui` \| `telegram` \| `slack` \| `cron` \| `api_server` |
| `user_id` | TEXT | 사용자 식별자 (NULL 가능) |
| `model` | TEXT | 사용 모델명 (예: `claude-opus-4-7`, `Qwen3.6-35B-A3B-FP8`) |
| `parent_session_id` | TEXT FK | NULL = root 세션, 값 있음 = context compression 분기 |
| `started_at` | REAL | Unix epoch **초** (float) |
| `ended_at` | REAL | Unix epoch 초. NULL = 진행 중 |
| `end_reason` | TEXT | 종료 이유 (아래 참조) |
| `message_count` | INTEGER | 세션 내 메시지 수 |
| `tool_call_count` | INTEGER | 도구 호출 횟수 |
| `api_call_count` | INTEGER | API 호출 횟수 |
| `input_tokens` | INTEGER | 입력 토큰 합계 |
| `output_tokens` | INTEGER | 출력 토큰 합계 |
| `cache_read_tokens` | INTEGER | 캐시 읽기 토큰 |
| `cache_write_tokens` | INTEGER | 캐시 쓰기 토큰 |
| `reasoning_tokens` | INTEGER | Extended thinking 토큰 |
| `billing_provider` | TEXT | 청구 제공자 |
| `billing_mode` | TEXT | 청구 방식 |
| `estimated_cost_usd` | REAL | 추정 비용 |
| `actual_cost_usd` | REAL | 실제 청구 비용 |
| `cost_status` | TEXT | 비용 계산 상태 (`unknown` 등) |
| `title` | TEXT | 세션 제목 (UNIQUE, NULL 가능) |

> **비용 컬럼 우선순위**: `COALESCE(actual_cost_usd, estimated_cost_usd)`
> **캐시 히트율**: `cache_read_tokens / (input_tokens + cache_read_tokens) × 100`

**`end_reason` 값 목록**

| 값 | 설명 |
|----|------|
| `cli_close` | CLI 세션 종료 |
| `tui_close` / `tui_shutdown` | TUI 세션 종료 |
| `cron_complete` | 크론 작업 완료 |
| `session_reset` | 세션 리셋 |
| `new_session` | 새 세션으로 전환 |
| `compression` | 컨텍스트 압축 |
| NULL | 비정상 종료 또는 진행 중 |

### messages

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | INTEGER PK | 자동 증가 |
| `session_id` | TEXT FK | → `sessions.id` |
| `role` | TEXT | `user` \| `assistant` \| `tool` \| `session_meta` |
| `content` | TEXT | 메시지 본문 |
| `tool_calls` | TEXT (JSON) | 도구 호출 배열 (role=assistant일 때) |
| `tool_name` | TEXT | 호출된 도구 이름 (role=tool일 때) |
| `timestamp` | REAL | Unix epoch 초 |
| `finish_reason` | TEXT | `stop` \| `tool_calls` |
| `reasoning` | TEXT | Extended thinking 원문 |
| `token_count` | INTEGER | 해당 메시지 토큰 수 |

---

## 5. messages.tool_calls JSON 구조

```json
[
  {
    "id": "call_function_xxx",
    "call_id": "call_function_xxx",
    "type": "function",
    "function": {
      "name": "terminal",
      "arguments": "{\"command\": \"ls -la\"}"
    }
  }
]
```

> 도구명 추출: `json_extract(value, '$.function.name')` + `json_each(tool_calls)`
> `tool_name` 컬럼은 role=tool 행에만 채워짐. role=assistant의 도구 호출은 `tool_calls` JSON에서 추출.

---

## Appendix

### A. 공통 제약

- 타임스탬프는 **초 단위 float** → `date(col, 'unixepoch')` (OpenCode의 밀리초와 다름)
- 비용: `COALESCE(actual_cost_usd, estimated_cost_usd)` 패턴 사용
- 루트 세션만 집계: `WHERE parent_session_id IS NULL` (중복 집계 방지)
- 진행 중 세션 제외: `WHERE ended_at IS NOT NULL`
- 스키마 버전 확인: `SELECT version FROM schema_version;` (현재: 11)

### B. 인덱스 (성능 참고)

```
idx_sessions_source    ON sessions(source)
idx_sessions_parent    ON sessions(parent_session_id)
idx_sessions_started   ON sessions(started_at DESC)
idx_messages_session   ON messages(session_id, timestamp)
```

### C. FTS5 검색

```sql
-- 전문 검색 (영문)
SELECT rowid FROM messages_fts WHERE messages_fts MATCH 'keyword';

-- 부분 문자열 / CJK 검색
SELECT rowid FROM messages_fts_trigram WHERE messages_fts_trigram MATCH '검색어';
```

> FTS5 인덱스는 `content + tool_name + tool_calls` 를 합쳐서 색인.

### D. 프로파일 DB 통합 조회 패턴

```bash
for db in ~/.hermes/state.db ~/.hermes/profiles/*/state.db; do
  [ -f "$db" ] || continue
  sqlite3 "$db" "SELECT ..."
done
```

### E. 관련 문서

- `hermes-monitoring-guide.md` — 무엇을 왜 모니터링할지 지표 정의
