---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/20"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 20
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-10T02:07:49Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #20: feat: shutdown cleanup + ErrorClassifier promotion (Phase 3)

## Summary
- Promote `ErrorClassifier` / `ErrorSeverity` from websocket-only to `src/core/error_classifier.py` for project-wide use
- Add backward-compatible re-export in `src/services/websocket_service/error_classifier.py` (extends with `WebSocketDisconnect`, `ValidationError`)
- Enhance `_shutdown()` in `main.py`: reverse-order teardown (sweep → channel → websocket → MongoDB)
- Add `WebSocketManager.close_all()` to drain active connections on shutdown
- Add `SlackService.cleanup()` and `cleanup_channel_service()` for Slack HTTP client teardown
- Apply `ErrorClassifier.classify()` in `service_manager._initialize_service()` for severity-aware error logging
- Add `severity` field to `ModuleStatus` and classify health check failures in `health.py`

## Test plan
- [x] `tests/core/test_error_classifier.py` — 14 tests covering classify, should_retry, get_backoff_delay, subclass inheritance
- [x] `tests/services/test_shutdown_cleanup.py` — 7 tests covering sweep stop, Slack cleanup, WS close_all
- [x] `sh scripts/lint.sh` — ruff + black + 9 structural tests all pass
- [x] 24 total new tests passing

🤖 Generated with [Claude Code](https://claude.com/claude-code)
