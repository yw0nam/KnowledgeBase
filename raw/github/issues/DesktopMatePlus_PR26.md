---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/26"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 26
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-11T11:35:55Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #26: feat: fix MCP client lifecycle for langchain-mcp-adapters 0.2.2

## Summary
- Fix MCP tool loading for `langchain-mcp-adapters 0.2.2` (stateless API, no context manager)
- Replace `__aenter__/__aexit__` lifecycle with direct `await client.get_tools()`
- Graceful degradation: MCP failure logs exception, agent continues without MCP tools
- Add commented code-sandbox MCP config example (Docker isolation)

**Depends on:** #feat/phase6a-builtin-tools (base branch)

## Files
- `src/services/agent_service/openai_chat_agent.py` — Stateless MCP pattern
- `src/main.py` — Cleanup in shutdown (no-op)
- `yaml_files/services/agent_service/openai_chat_agent.yml` — Code-sandbox example
- `tests/services/agent_service/test_mcp_lifecycle.py` — 3 lifecycle tests

## Test plan
- [x] 565 unit tests pass
- [x] MCP graceful degradation verified (get_tools() failure → empty tools, no crash)
- [x] Lint pass

🤖 Generated with [Claude Code](https://claude.com/claude-code)
