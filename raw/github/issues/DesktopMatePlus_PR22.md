---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/22"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 22
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-10T13:55:17Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #22: refactor: unify channel/sweep YAML parsing into service_manager

## Summary

- Move inline YAML parsing from `main.py` `_startup()` into `initialize_channel_service()` and `initialize_sweep_service()` in `service_manager.py`
- Matches existing pattern used by TTS/Agent/LTM services
- Graceful degradation when config files missing (warning log + defaults, not crash)
- Env var fallbacks for Slack credentials (`SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`) preserved

## Test plan

- [x] `sh scripts/lint.sh` — ruff + black + structural tests passed
- [x] `uv run pytest tests/ -x -q --ignore=tests/e2e` — 497 passed, 0 failures
- [x] 11 new tests: YAML loading, env var fallback, missing file graceful degradation, sweep dependency wiring
- [x] PR review toolkit: code + errors + tests — all PASS after fixes
- [ ] E2E skipped (MongoDB/Qdrant not running — refactoring only, no behavior change)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
