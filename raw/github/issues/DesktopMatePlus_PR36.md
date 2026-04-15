---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/36"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 36
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-14T07:22:01Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #36: feat: Human-in-the-Loop approval gate for dangerous tool calls

## Summary

- Implement HitL Phase 1 MVP — LangGraph `interrupt()`-based approval gate that pauses agent execution when invoking dangerous tools (MCP + `delegate_task`), sends `hitl_request` via WebSocket, and waits for user approval/denial before proceeding
- Add `HitLMiddleware` following existing `ToolGateMiddleware` pattern, with shared `_consume_astream` helper for stream processing
- Wire full WS layer: event handling, message routing, turn state management (`AWAITING_APPROVAL`), and graph resume via `Command(resume=...)`

## Changes

### New files
- `src/services/agent_service/middleware/hitl_middleware.py` — middleware calling `interrupt()` for dangerous tools
- `tests/unit/test_hitl_models.py` — 10 tests for message types and turn status
- `tests/unit/test_hitl_middleware.py` — 7 tests for tool classification and interrupt behavior
- `tests/unit/test_hitl_agent_stream.py` — 7 tests for interrupt detection and resume
- `tests/unit/test_hitl_event_handling.py` — 9 tests for WS layer event handling
- `tests/e2e/test_hitl_e2e.py` — 9 E2E tests for full approve/deny/multi-tool flows
- `tests/spike/test_interrupt_in_middleware.py` — spike validating `interrupt()` in middleware

### Modified files
- `src/models/websocket.py` — `HITL_REQUEST/RESPONSE` message types + Pydantic models
- `src/services/agent_service/openai_chat_agent.py` — `_consume_astream` shared helper, `resume_after_approval()`
- `src/services/websocket_service/message_processor/models.py` — `TurnStatus.AWAITING_APPROVAL`
- `src/services/websocket_service/message_processor/event_handlers.py` — `hitl_request` handler in producer
- `src/services/websocket_service/message_processor/processor.py` — `stream_events` hitl termination, `attach_agent_stream` reset, interrupt during approval
- `src/services/websocket_service/manager/handlers.py` — `handle_hitl_response()`
- `src/services/websocket_service/manager/websocket_manager.py` — `HITL_RESPONSE` routing
- `docs/known_issues/KNOWN_ISSUES.md` — KI-22: safe_tool E2E non-determinism

## Test plan

- [x] 33 unit tests passing (models, middleware, agent stream, WS event handling)
- [x] 9 E2E tests (approve, deny, multi-tool, safe tool bypass, existing flow unchanged)
- [x] Lint clean (ruff + black + 23 structural tests)
- [x] Full regression suite: 642 passed, 0 failures
- [x] `bash scripts/e2e.sh` → PASSED

🤖 Generated with [Claude Code](https://claude.com/claude-code)
