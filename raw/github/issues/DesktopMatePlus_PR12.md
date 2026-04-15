---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/12"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 12
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-04T08:10:48Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #12: fix(agent): prevent persona SystemMessage duplicate injection and fix STM delete

## Summary

**Bug fix: Persona SystemMessage ordering violations (OpenAI 400 errors)**

- **`invoke()` duplicate injection**: Added `and not session_id` guard matching the existing `stream()` fix. Continuing sessions restored from checkpointer already have a SystemMessage at position 0 — injecting a second one caused OpenAI `System message must be at the beginning` 400 errors.
- **`ltm_retrieve_hook` injection fix**: LTM memories were being appended as a new `SystemMessage` after `HumanMessage` in the message list. Fixed to only update (in-place via matching id) the existing `SystemMessage` at position 0. If no such message exists, injection is skipped to avoid ordering violations.
- **STM `add_chat_history` registry gap**: Added `session_registry.upsert()` call after `update_state` so sessions created via the REST API are registered and deletable.
- **STM `delete_session` incomplete**: Added `checkpointer.delete_thread()` call to purge LangGraph checkpoint data alongside the registry entry, so GET after DELETE correctly returns 0 messages.

## Test Coverage

All new code paths covered:

- `test_invoke_injects_persona_only_for_new_session` — invoke() with session_id set must NOT inject SystemMessage
- `test_invoke_injects_persona_for_new_session` — invoke() with empty session_id MUST inject SystemMessage
- `test_stm` e2e: ADD → GET → DELETE → VERIFY-EMPTY round-trip PASSED

Tests: 5 → 7 (+2 new)

## Pre-Landing Review

No issues found.

## Test plan
- [x] `uv run pytest tests/agents/test_openai_chat_agent.py -v` — 7/7 PASSED
- [x] `uv run pytest` (full suite) — all passed
- [x] `sh scripts/lint.sh` — all checks passed
- [x] `bash scripts/e2e.sh` — Phase 4 OK, Phase 5 OK (no ERROR lines)
  - test_stm: STM PASSED
  - test_websocket: Turn1 + Turn2 both stream_end OK

🤖 Generated with [Claude Code](https://claude.com/claude-code)
