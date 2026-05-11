# OpenCode Monitoring Guide — Daily & Weekly Report

Updated: 2026-05-11 (rev4)

## 1. Synopsis

- **Purpose**: OpenCode DB에서 어떤 데이터를 왜 모니터링해야 하는지 정의. 쿼리는 에이전트가 이 문서를 보고 생성.
- **DB**: `~/.local/share/opencode/opencode.db` — 스키마 상세는 `opencode-schema-reference.md` 참조.

---

## 2. 모니터링 지표 정의

### Layer 1: 비용·효율 (Cost & Efficiency)

**목적**: 얼마나 썼나, 낭비는 없나.

> ⚠️ **모델별 토큰은 Prometheus 우선**: SQLite `session.model`은 subagent 세션에서 전부 NULL.
> 실제 모델 분포(haiku, sonnet, gpt 등)는 Prometheus `opencode_token_usage_tokens_total{model="..."}` 에서만 확인 가능.
> SQLite 단독 집계 시 shadow 비용이 과대 계산된다.

| 지표 | 소스 | 의미 |
|------|------|------|
| 모델별 일일 토큰 | **Prometheus** `opencode_token_usage_tokens_total` by model, type | 실제 모델 분포 확인. SQLite는 subagent model=NULL |
| 모델별 실청구 비용 | **Prometheus** `opencode_cost_usage_USD_total` by model | 구독 세션은 0, API 과금 모델만 찍힘 |
| shadow 비용 | Prometheus 토큰 × pricing-exporter 단가 | 구독 절감액 산출 |
| 캐시 히트율 | `cacheRead / (input + cacheRead) × 100` | 높을수록 비용 효율 좋음. 실측 평균 97% |
| API 호출 횟수 | SQLite `step-finish` count per session | 평균 16회. 51회+ = 루프 탈출 실패 의심 |
| reasoning 토큰 비율 | Prometheus `type="reasoning"` / 전체 | Extended thinking 남용 여부 |
| 세션별 토큰 이상치 | 상위 5% 세션 | 목적 대비 과도한 소비 여부 검토 |

### Layer 2: 작업 품질 (Task Quality)

**목적**: 작업이 완료됐나, 어디서 막혔나.

| 지표 | 소스 | 의미 |
|------|------|------|
| Todo 완료율 | `todo.status` | 전체 평균 80.9%. 세션 완료율 0% = 중단된 작업 |
| 도구별 에러율 | `tool.state.status = error` | webfetch 12.8%, write 5.1%, edit 3.9% |
| 연속 에러 세션 | 같은 도구가 동일 세션에서 2회+ 실패 | 에이전트가 막혀서 반복 실패하는 구간 |
| compaction 발생 | `part.type = compaction` | 세션이 너무 길어짐 → 분할 검토 |
| step-finish reason=error | `step-finish.reason = error` | API 레벨 실패 (드묾, 실측 2건) |

### Layer 3: 행동 패턴 (Behavioral Patterns)

**목적**: 언제, 어떻게 일하나 — 습관 최적화.

| 지표 | 소스 | 의미 |
|------|------|------|
| 시간대별 세션 분포 | `session.time_created` hour | 실측: 새벽 1~3시 집중(150개), 낮 저활동 |
| 요일별 활동량 | `session.time_created` weekday | 실측: 월요일 136개로 압도적 1위 |
| root vs subagent 비율 | `session.parent_id IS NULL` | 실측: root 86개 vs subagent 249개 (위임율 74%) |
| 도구 사용 믹스 | `tool.tool` 분포 | read > bash > grep 순. 탐색 vs 실행 비율 |
| 세션 길이 분포 | `step-finish` count per session | short(35%) / medium(40%) / long(18%) / very long(6%) |

### Layer 4: 집중도·안정성 (Focus & Stability)

**목적**: 어디에 집중했나, 무엇이 불안정한가.

| 지표 | 소스 | 의미 |
|------|------|------|
| 일일 프로젝트 전환 수 | SQLite `session.project_id` distinct per day | 3개+ = 컨텍스트 스위칭 과다 |
| 핫 파일 (주간 수정 빈도) | SQLite `patch.files[]` | 반복 수정 = 설계 불안정. 실측: mail_server.py 46회 |
| 세션당 수정 파일 수 | SQLite `patch.files[]` distinct per session | 과도하게 많으면 범위 초과 작업 |
| 모델별 세션 분포 (root) | SQLite `session.model.id` | root 세션만 유효. subagent는 NULL이므로 Prometheus 참조 |
| 모델별 세션 분포 (전체) | **Prometheus** `opencode_token_usage_tokens_total` by model | subagent 포함 실제 모델 분포 |

---

## 4. 신호 → 액션 매핑

| 신호 | 임계값 | 액션 |
|------|--------|------|
| API 호출 횟수 | 세션 > 50회 | 루프 탈출 실패 여부 확인, 세션 분할 검토 |
| 도구 에러율 | 도구별 > 5% | retry 로직 추가 또는 대체 도구 검토 |
| Todo 완료율 | 세션 < 50% | 중단 원인 분석 (계획 과다? 실행 실패?) |
| compaction 발생 | 1회 이상 | 세션 분할 또는 컨텍스트 정리 전략 수립 |
| 일일 프로젝트 전환 | > 3개 | 집중도 저하 경고 |
| 핫 파일 수정 횟수 | 주간 > 10회 | 설계 불안정 → 리팩토링 우선순위 상향 |
| reasoning 토큰 비율 | > 30% | Extended thinking 사용 타당성 검토 |

---

## Appendix

### A. 관련 문서

- `opencode-schema-reference.md` — 테이블·컬럼·JSON 구조 상세

### B. PatchNote

2026-05-11: 최초 작성.
2026-05-11 (rev2): 캐시 히트율 계산식 오류 수정.
2026-05-11 (rev3): 문서 전면 재구성. 쿼리 제거, 스키마·지표 정의 중심으로 재작성.
2026-05-11 (rev4): §2 Source Schema 제거 (opencode-schema-reference.md로 이관). Appendix A·B 제거.
2026-05-11 (rev5): Layer 1에 Prometheus 우선 지표 추가 및 SQLite model=NULL 한계 경고 명시. Layer 4에 모델별 세션 분포 소스 분리 (root=SQLite, 전체=Prometheus).
