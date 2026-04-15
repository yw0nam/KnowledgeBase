---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/27"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 27
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-11T11:36:03Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #27: feat: add ToolGateMiddleware for defense-in-depth tool validation

## Summary
- Add `ToolGateMiddleware` as defense-in-depth layer for shell and filesystem tool calls
- Shell gating: metacharacter rejection (`; | & $ \``), `shlex.split()`, whitelist enforcement
- Filesystem gating: `Path.resolve()` + `relative_to()` for allowed-dir enforcement
- Fail-closed: `None` = inactive, `[]` = deny all
- Generic error messages (no whitelist/path leaks to LLM)
- Middleware positioned first in chain (before DelegateToolMiddleware)

**Depends on:** #feat/phase6a-builtin-tools (base branch)

## Files
- `src/services/agent_service/middleware/tool_gate_middleware.py` — Gate middleware
- `src/services/agent_service/openai_chat_agent.py` — Middleware chain integration
- `tests/services/agent_service/middleware/test_tool_gate_middleware.py` — 29 tests

## Test plan
- [x] 591 unit tests pass
- [x] Shell bypass tests: `;`, `&&`, `|`, `$()`, backtick, `\n` all blocked
- [x] Filesystem traversal tests: `../` blocked, symlink resolved
- [x] Fail-closed: empty allowlist blocks all
- [x] Info leak test: error messages don't contain whitelist
- [x] Security review pass

🤖 Generated with [Claude Code](https://claude.com/claude-code)
