---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/35"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 35
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-14T00:02:51Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #35: test: resolve KI-18/19/20 — E2E teardown, async gen fix, severity assertion

## Summary

- **KI-18**: `stm_session` E2E fixture changed `return` → `yield` with teardown calling `DELETE /v1/stm/sessions/{id}`, preventing MongoDB session accumulation and spurious `task_sweep` ERROR logs
- **KI-19**: `_ConcreteAgent.stream` in test helper drops unreachable `return` before `yield`, making it a valid async generator and resolving basedpyright `reportIncompatibleMethodOverride` warning
- **KI-20**: `test_health_endpoint` unhealthy mock now includes `severity` on each `ModuleStatus`; assertions verify `severity` serializes as `"transient"|"recoverable"|"fatal"` and structure test checks `"severity" in module`
- **KI-21**: Closed as Won't Fix — investigation confirmed `run.sh` already references `services.yml` correctly; no issue present
- `KNOWN_ISSUES.md`: all four items updated (`[x]` or closed with rationale)

## Test plan

- [x] `uv run pytest tests/services/agent_service/test_agent_service_base.py tests/api/test_health_endpoint.py` — 11/11 passed
- [x] `sh scripts/lint.sh` — ruff + black + 23 structural tests passed
- [ ] `sh scripts/e2e.sh` — KI-18 teardown requires live infra; verify manually when services are up

🤖 Generated with [Claude Code](https://claude.com/claude-code)
