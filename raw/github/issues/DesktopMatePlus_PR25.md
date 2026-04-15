---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/25"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 25
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-11T11:35:49Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #25: feat: add builtin tools with YAML-driven tool registry

## Summary
- Add `ToolRegistry` with YAML config-driven tool enable/disable
- LangChain builtin tools: filesystem (ReadFile/WriteFile/ListDir), shell (command whitelist), DuckDuckGo search
- Pydantic V2 models for `ToolConfig` validation at startup
- Shell security: `shlex.split()` + `shell=False` + metacharacter rejection
- All tools disabled by default for safety

## Files
- `src/services/agent_service/tools/registry.py` — Tool registry
- `src/services/agent_service/tools/builtin/` — Filesystem, shell, search tool wrappers
- `src/configs/agent/openai_chat_agent.py` — Pydantic ToolConfig models
- `yaml_files/services/agent_service/openai_chat_agent.yml` — tool_config section
- `tests/services/agent_service/tools/test_registry.py` — 18 tests including injection bypass

## Test plan
- [x] 568 unit tests pass
- [x] Shell injection bypass tests (`;`, `&&`, `|`, `$()`) all blocked
- [x] Lint pass
- [x] Security review: shell=False, metacharacter rejection, no type:ignore

🤖 Generated with [Claude Code](https://claude.com/claude-code)
