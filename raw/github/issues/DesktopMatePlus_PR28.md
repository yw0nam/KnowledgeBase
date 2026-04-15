---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/28"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 28
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-13T00:21:36Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #28: refactor: resolve known issues KI-10, KI-12, KI-13, KI-15

## Summary

- **KI-10**: `ModuleStatus.severity` 타입 `str | None` → `ErrorSeverity | None` 강화, `classify_health_severity()` 모듈 레벨 함수로 추출
- **KI-13**: base `AgentService`에 `cleanup_async()` no-op 추가, `main.py`의 `hasattr` 가드 제거
- **KI-12**: tool factory 중복 로깅 제거, `ToolRegistry` 로그에 config 상세 정보 추가
- **KI-15**: `initialize_channel_service()` 내 중복 `import os` 로컬 임포트 제거

## Test plan

- [x] `make lint` — ruff + black + 23 structural tests passed
- [x] `make test` — 610 passed (pre-existing 2 failures unrelated)
- [x] KI-10 severity 단위 테스트 4건 추가 (`tests/services/test_health_severity.py`)
- [x] KI-13 cleanup_async 테스트 2건 추가 (`tests/services/agent_service/test_agent_service_base.py`)
- [ ] `make e2e` — **미검증** (YAML 설정 통합 작업 별도 진행 중, MongoDB 인증 불일치로 E2E 환경 미동작 상태)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
