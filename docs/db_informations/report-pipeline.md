# Report Pipeline — Daily & Weekly

Updated: 2026-05-11

## 1. Synopsis

- **Purpose**: OpenCode + Hermes DB 기반 daily/weekly 리포트 파이프라인 설계 및 운영 규칙
- **형식**: 모든 리포트는 Markdown. 저장 위치: `data/wiki/summaries/`

---

## 2. 파이프라인 구조

```
SQLite (OpenCode + Hermes)          Prometheus OTel
  session / part / todo               opencode_token_usage_tokens_total
  patch.files / compaction            opencode_cost_usage_USD_total
        │                                       │
        └──────────────┬────────────────────────┘
                       ▼
            [daily cron 00:10 KST]
                       └── data/wiki/summaries/daily/YYYY-MM-DD_agent_usage.md
                                       │
                                       ▼
                       [weekly cron 월 06:00 KST]
                       └── data/wiki/summaries/weekly/YYYY-WNN_agent_usage.md
                                       │
                                       ▼
                       [monthly cron 1일 06:00 KST]  ← optional
                       └── data/wiki/summaries/monthly/YYYY-MM_agent_usage.md
```

### 소스별 역할 분담

| 소스 | 담당 지표 | 이유 |
|------|----------|------|
| SQLite `opencode.db` | 세션 수, root/subagent 구분, todo, 핫 파일, compaction, 시간대 분포 | 세션 구조 정보는 DB가 정확 |
| **Prometheus** | 모델별 토큰, shadow 비용, 실청구 비용 | subagent `session.model`이 DB에서 전부 NULL — OTel에만 실제 모델명 기록 |
| SQLite `hermes/state.db` | Hermes 전체 지표 | Hermes는 OTel 미연동 |

> **SQLite model=NULL 문제**: OpenCode subagent 세션은 `session.model` 컬럼이 NULL로 기록된다 (upstream 버그).
> Prometheus `opencode_token_usage_tokens_total{model="..."}` 에만 실제 모델명이 남으므로,
> 모델별 토큰·비용은 반드시 Prometheus에서 가져온다. SQLite 단독 집계 시 shadow 비용이 과대 계산된다.

---

## 3. 공통 규칙

### 날짜 경계
- 기준: **KST (UTC+9)** 자정 기준 하루
- 세션 귀속: `session.time_created` (세션 시작일) 기준
- 쿼리 구간: `00:00:00 KST <= time_created < 00:00:00 KST 다음날`
- OpenCode: `time_created/1000` (밀리초 → 초 변환 후 `unixepoch`)
- Hermes: `started_at` (이미 초 단위)

### 공백일 처리
- 데이터가 없는 날도 파일 생성
- 내용: 헤더 + `데이터 없음` 한 줄

### 파일명 규칙
- Daily: `YYYY-MM-DD_agent_usage.md` (예: `2026-05-10_agent_usage.md`)
- Weekly: `YYYY-WNN_agent_usage.md` (예: `2026-W20_agent_usage.md`, ISO 주차)
- Monthly: `YYYY-MM_agent_usage.md` (예: `2026-05_agent_usage.md`)

### Weekly 생성 방식
- **daily.md 7개를 직접 읽어 종합** (DB 재쿼리 없음)
- 누락 파일이 있으면 해당 날짜를 "데이터 없음"으로 표기
- LLM 입력: 7개 daily.md 전문 → 출력: weekly.md narrative

---

## 4. 템플릿

- Daily: [`templates/summary-daily_agent_usage.md`](../../templates/summary-daily_agent_usage.md)
- Weekly: [`templates/summary-weekly_agent_usage.md`](../../templates/summary-weekly_agent_usage.md)

**공백일 처리**: 데이터가 없는 날은 frontmatter만 채우고 본문을 `> 데이터 없음` 한 줄로 작성.

## 5. 비용 계산

### 실청구 vs Shadow

- **실청구**: Prometheus `opencode_cost_usage_USD_total` (모델별). 구독 세션은 0으로 찍힘.
- **Shadow**: 토큰 × LiteLLM 단가. 구독이어도 반드시 계산해서 기재.

### 단가 조회

```bash
curl -s localhost:9091/metrics | grep 'model_pricing_usd_per_token' | grep -v '#'
```

pricing-exporter(`/home/spow12/observability/pricing-exporter/server.py`)가 LiteLLM GitHub JSON을 24h 캐시로 제공.

### 모델 처리 규칙

| 상황 | 처리 |
|------|------|
| Prometheus에 model 레이블 있음 | 해당 단가로 shadow 계산 |
| pricing-exporter에 단가 없는 모델 | shadow 제외, 실청구만 기재, 명시적으로 표기 |
| claude max / codex 구독 세션 | 실청구 0 USD, shadow는 반드시 계산 |

### Shadow 계산식

```
shadow = input × p_input + output × p_output
       + cache_read × p_cache_read + cache_write × p_cache_write
       + reasoning × p_input   # reasoning은 input 단가 적용
```

---

## Appendix

### A. 저장 경로 전체

```
data/wiki/summaries/
├── daily/
│   ├── 2026-05-10_agent_usage.md
│   ├── 2026-05-11_agent_usage.md
│   └── ...
├── weekly/
│   ├── 2026-W19_agent_usage.md
│   └── ...
└── monthly/
    └── 2026-05_agent_usage.md
```

### B. 신호→액션 매핑 참조

daily/weekly 작성 시 아래 문서의 임계값 기준으로 이상 신호 판단:
- `opencode-monitoring-guide.md` §4
- `hermes-monitoring-guide.md` §3

### C. PatchNote

2026-05-11: 최초 작성. markdown 단일 형식, 세션 시작일 귀속, 공백일 파일 생성 방식으로 확정.
2026-05-11 (rev2): 데이터 소스 전략 추가. SQLite + Prometheus 조합 방식으로 전환. §2 파이프라인 구조에 소스별 역할 분담 표 추가. §5 비용 계산 전면 재작성.
