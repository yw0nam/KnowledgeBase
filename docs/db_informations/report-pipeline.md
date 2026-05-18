# Report Pipeline — Daily & Weekly

Updated: 2026-05-11

## 1. Synopsis

- **Purpose**: OpenCode + Hermes DB 기반 daily/weekly 리포트 파이프라인 설계 및 운영 규칙
- **형식**: 모든 리포트는 Markdown. 저장 위치: `data/wiki/summaries/`

---

## 2. 파이프라인 구조

```
SQLite (OpenCode)                   SQLite (Hermes)
  message / session / part / todo     sessions
  patch.files / compaction                  │
        │                                   │
        └──────────────┬────────────────────┘
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
| `message.data` (modelID, tokens, cost) | **모델별 토큰·실청구·shadow** | root+subagent 구분 없이 실제 모델명 기록. 유일한 정확한 소스 |
| `session` (parent_id, time_created) | 세션 수, root/subagent 구분, 시간대 분포, 프로젝트별 분포 | 세션 구조 정보 |
| `part` (type=tool, patch, compaction) | 도구 에러율, 핫 파일, compaction | 세션 내 행동 데이터 |
| `todo` | Todo 완료율 | 작업 품질 |
| SQLite `hermes/state.db` | Hermes 전체 지표 | Hermes는 OTel 미연동, DB가 유일 소스 |

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

- Daily: [`templates/wiki/summaries/daily_agent_usage.md`](../../templates/wiki/summaries/daily_agent_usage.md)
- Weekly: [`templates/wiki/summaries/weekly_agent_usage.md`](../../templates/wiki/summaries/weekly_agent_usage.md)

**공백일 처리**: 데이터가 없는 날은 frontmatter만 채우고 본문을 `> 데이터 없음` 한 줄로 작성.

## 5. 비용 계산

### 비용 소스

- **기록 비용**: `SUM(message.data.cost)`. OpenCode가 모든 모델에 대해 자동 집계.

### providerID별 처리 규칙

| providerID | 비용 소스 |
|------------|----------|
| `anthropic` | `message.data.cost` (OpenCode 자동 집계) |
| `openai` | `message.data.cost` (OpenCode 자동 집계) |
| `google` | `message.data.cost` (OpenCode 자동 집계) |
| `opencode-go` | `message.data.cost` (실청구) |
| `vllm` | 0 USD (자체호스팅, 집계 제외) |

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
