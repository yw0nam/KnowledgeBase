---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/24"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 24
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-11T11:35:40Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #24: refactor: unify channel/sweep YAML loading with shared helper

## Summary
- Extract `_load_service_yaml()` helper in `service_manager.py` to deduplicate YAML loading pattern
- `initialize_channel_service()` and `initialize_sweep_service()` now use the shared helper
- Preserves all existing behavior (env var fallbacks, runtime deps)

## Test plan
- [x] 550 unit tests pass
- [x] Lint (black + ruff + structural) pass
- [x] Code review: APPROVE (0 critical, 0 high)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
