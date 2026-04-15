---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/23"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 23
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-10T14:48:32Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #23: feat: user profile and conversation summarization (Phase 7)

## Summary

- **User Context Profile**: MongoDB-backed UserProfile CRUD + agent middleware injection + UpdateUserProfileTool for automatic profile learning from conversations
- **Conversation Summarization**: LLM-based STM compression after configurable turn threshold (default 20). Fire-and-forget async with 60s timeout, GC-safe task references
- Middleware chain: profile → summary → LTM (before model), LTM → summary (after model)

### Review fixes applied
- `initialize_summary_service()` wired in main.py startup
- Regex-based summary section replacement preserves profile data
- ChatOpenAI fallback logged at WARNING
- All service inits isolated in own try-except
- Tool error handling with graceful messages

## Test plan

- [x] `sh scripts/lint.sh` — ruff + black + structural tests passed
- [x] `uv run pytest tests/ -x -q --ignore=tests/e2e` — 533 passed, 0 failures
- [x] 19 new tests: profile CRUD (3), profile middleware (3), update tool (3), summary service (9), summary middleware (10)
- [x] PR review toolkit: code + errors — Critical/High issues fixed
- [ ] E2E skipped (MongoDB/Qdrant not running)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
