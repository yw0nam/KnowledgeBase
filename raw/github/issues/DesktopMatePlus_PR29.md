---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/29"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 29
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-13T02:24:58Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #29: refactor: unify fragmented service YAML configs

## Summary

- `yaml_files/services/` 하위 파편화된 10+ 개별 서비스 YAML을 환경별 standalone 파일 3개로 통합 (`services.yml`, `services.docker.yml`, `services.e2e.yml`)
- `load_main_config()`을 N개 서비스 경로 대신 단일 `services_file` 키로 단순화
- 모든 `initialize_*` 함수의 default path를 `services.yml`로 통일
- e2e.sh: `YAML_FILE=yaml_files/e2e.yml` 자동 설정 + 로그 파일 정리 (stale log 누적 방지)
- `TestBackendConnectivity`, `TestBackendCallbackDirect`에 `@pytest.mark.e2e` 마커 추가 (unit test에서 잘못 실행되던 문제 수정)

## Test plan

- [x] `make lint` PASS
- [x] `make test` PASS (600 passed, 0 failed)
- [x] `make e2e` Phase 1-4 ALL PASS (6 passed, 16 skipped)
- [ ] Phase 5 sweep 에러는 KI-17 (LangGraph state 종속) — 별도 PR에서 해결

🤖 Generated with [Claude Code](https://claude.com/claude-code)
