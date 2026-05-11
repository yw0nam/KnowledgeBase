# Hermes Monitoring Guide — Daily & Weekly Report

Updated: 2026-05-11

## 1. Synopsis

- **Purpose**: Hermes DB에서 어떤 데이터를 왜 모니터링해야 하는지 정의. 쿼리는 에이전트가 이 문서를 보고 생성.
- **DB**: `~/.hermes/state.db` + `~/.hermes/profiles/*/state.db`

---

## 2. 모니터링 지표 정의

### Layer 1: 비용·효율 (Cost & Efficiency)

**목적**: 얼마나 썼나, 낭비는 없나.

| 지표 | 소스 | 의미 |
|------|------|------|
| 일일 총 비용 | `COALESCE(actual_cost_usd, estimated_cost_usd)` | 전날 대비 20%+ 증가 시 드릴다운 |
| 모델별 비용 점유율 | `sessions.model` + 비용 | 비싼 모델이 단순 task에 쓰이는지 확인 |
| 캐시 히트율 | `cache_read_tokens / (input_tokens + cache_read_tokens) × 100` | 낮으면 system prompt 구조 재검토 |
| reasoning 토큰 비율 | `reasoning_tokens / output_tokens` | thinking 모델에서 단순 task에 낭비되는지 확인 |
| API 호출 횟수 | `sessions.api_call_count` | 세션당 과도하면 루프 탈출 실패 의심 |

### Layer 2: 작업 품질 (Task Quality)

**목적**: 작업이 완료됐나, 어디서 막혔나.

| 지표 | 소스 | 의미 |
|------|------|------|
| 완료율 | `end_reason = 'cron_complete' 또는 'cli_close'` / 전체 | 실측: `cli_close` 31건, NULL(비정상) 24건 |
| end_reason 분포 | `sessions.end_reason` | `context_limit` 多 → compaction 설정 조정, `error` 多 → tool 실패 분석 |
| 진행 중 세션 수 | `ended_at IS NULL` | 비정상적으로 많으면 좀비 세션 의심 |
| 도구 호출 횟수 | `sessions.tool_call_count` | 세션당 평균 대비 3배+ = 루프 또는 반복 재시도 |
| context compression 발생 | `end_reason = 'compression'` 또는 `parent_session_id IS NOT NULL` | 세션 분할 또는 컨텍스트 정리 전략 수립 |

### Layer 3: 행동 패턴 (Behavioral Patterns)

**목적**: 언제, 어떻게, 어디서 일하나.

| 지표 | 소스 | 의미 |
|------|------|------|
| source별 세션 분포 | `sessions.source` | 실측: cli(37) > api_server(18) > telegram(12) > cron(11) > tui(10) |
| 시간대별 세션 분포 | `strftime('%H', started_at, 'unixepoch')` | 피크 시간대 파악, cron 스케줄 최적화 |
| 평균 세션 시간 | `AVG(ended_at - started_at)` | 길어지면 context 폭발 또는 tool 루프 의심 |
| 도구 사용 Top N | `messages.tool_calls` JSON 파싱 | 가장 많이 쓰는 도구 패턴 파악 |
| 세션당 도구 호출 빈도 | `tool_call_count / COUNT(sessions)` | 특정 도구가 평소의 3배면 루프 징후 |

### Layer 4: 프로파일별 분포 (Multi-Agent Focus)

**목적**: 어느 에이전트가 얼마나 일하는가.

| 지표 | 소스 | 의미 |
|------|------|------|
| 프로파일별 세션·비용 | 각 `profiles/*/state.db` | 에이전트별 부하 분산 확인 |
| 프로파일별 모델 사용 | `sessions.model` per profile | 에이전트별 모델 라우팅 정책 검증 |
| root vs subagent 비율 | `parent_session_id IS NULL` | 실측: root 85개 vs subagent 4개 |

---

## 3. 신호 → 액션 매핑

| 신호 | 임계값 | 액션 |
|------|--------|------|
| 일일 비용 급증 | 전날 대비 +20% | 해당일 세션 Top 5 드릴다운 |
| 캐시 히트율 저하 | < 30% | system prompt 구조 재검토 |
| NULL end_reason 비율 | > 20% | 비정상 종료 원인 분석 |
| 세션당 API 호출 | 평균 대비 3배+ | 루프 탈출 실패 여부 확인 |
| reasoning 토큰 비율 | > 30% | `max_thinking_tokens` 조정 검토 |
| context compression | 주간 3회+ | 세션 분할 전략 수립 |
| 특정 도구 호출 급증 | 평소 대비 3배+ | 루프 또는 반복 재시도 징후 |

---

## 4. Daily vs Weekly 분리 기준

```
Daily Report (어제 기준)              Weekly Report (지난 7일)
─────────────────────────             ──────────────────────────────
• 총 비용 / 세션 수 / 완료율           • 일별 비용·토큰 트렌드
• source별 사용 분포                   • 캐시 히트율 추이 (개선/악화)
• end_reason 분포                      • 모델별 비용 점유율
• 도구 사용 Top 10                     • 도구별 calls_per_session 트렌드
• 비정상 종료 세션 목록                • 피크 시간대 패턴
• 진행 중(좀비) 세션 수                • 프로파일별 부하 분산
```

---

## Appendix

### A. OpenCode와의 차이점

| 항목 | Hermes | OpenCode |
|------|--------|----------|
| 타임스탬프 단위 | **초** (float) | **밀리초** (integer) |
| 토큰 저장 위치 | `sessions` 테이블 컬럼 | `part` 테이블 JSON |
| 비용 컬럼 | `actual_cost_usd` / `estimated_cost_usd` 분리 | `part.step-finish.cost` |
| 도구 호출 기록 | `messages.tool_calls` JSON 배열 | `part.tool` JSON |
| 멀티 DB | 프로파일별 독립 DB | 단일 DB |
| FTS 지원 | ✅ (FTS5 + trigram) | ❌ |

### B. 관련 문서

- `hermes-schema-reference.md` — 테이블·컬럼·JSON 구조 상세
