---
type: summary
subtype: daily
date: ""
created: ""
updated: ""
sources: []
tags: []
---

# Daily Report — {{YYYY-MM-DD}}

## Summary

- OpenCode: 총 N세션 (root N / subagent N), 프로젝트 N개
- Hermes: 총 N세션, source N종
- 총 shadow 비용: N USD (OpenCode N USD + Hermes N USD)

## Layer 1: 비용·효율

**OpenCode**
- 총 토큰: N (input N / output N / cache_read N / cache_write N)
- 캐시 히트율: N%
- 실청구: N USD / Shadow: N USD
- 이상치: <!-- reasoning 비율 높은 세션, API 호출 50회+ 세션 제목과 함께 명시 -->

**Hermes**
- 총 토큰: N (input N / output N / cache_read N)
- 캐시 히트율: N%
- 실청구: N USD / Shadow: N USD (claude 계열만, 나머지 단가 불명확)
- 모델별 분포: <!-- model: N세션 형식 -->

## Layer 2: 작업 품질

**OpenCode**
- Todo 완료율: N% (N/N)
- 도구 에러: <!-- tool N% (N/N) 형식, 에러 있는 도구만 -->
- compaction: N건

**Hermes**
- end_reason 분포: <!-- cli_close N / cron_complete N / NULL N 형식 -->
- 좀비 세션 (ended_at IS NULL): N건

## Layer 3: 행동 패턴

**OpenCode**
- 시간대 분포: <!-- 피크 시간대 중심으로 기술 -->
- root vs subagent: root N / subagent N (위임율 N%)

**Hermes**
- source 분포: <!-- cli N / tui N / cron N / telegram N 형식 -->
- 평균 세션 시간: N초 (약 N분)

## Layer 4: 집중도·안정성

**OpenCode**
- 프로젝트 전환: N개 <!-- 3개+ 경고 -->
- 핫 파일: <!-- 수정 빈도 상위 파일 -->
- 세션당 수정 파일 수: 평균 N개, 최대 N개

**Hermes**
- root vs subagent: root N / subagent N
- 모델별 세션: <!-- model: N세션 형식 -->

## Observations

<!-- Layer 1~4에서 포착되지 않은 주목할 패턴, 이상 징후, 맥락 자유 기록 -->
<!-- 없으면 생략 가능 -->
