---
source_url: "https://github.com/yw0nam/DesktopMatePlus/blob/main/CLAUDE.md"
type: claude_md
repo: "yw0nam/DesktopMatePlus"
captured_at: "2026-04-15T00:43:20Z"
commit: "91d2c3b1180c2ad34c4ea8cc7238ad24767d7a21"
contributor: "nam-young-woo"
tags: [project]
---

# PROJECT KNOWLEDGE BASE

**Generated:** 2026-04-14
**Commit:** 9975c71
**Branch:** master

## OVERVIEW

DesktopMate+ backend — Python 3.13 / FastAPI server for AI desktop companion (Yuri). WebSocket streaming chat, TTS synthesis (IrodoriTTS), LangChain/LangGraph agent with MCP tools, MongoDB STM, mem0 LTM, Slack channel integration, background task sweep. No GPU inference in-process — calls OpenAI, vLLM, IrodoriTTS, MongoDB, Qdrant externally.

## Tech Stack

- **Runtime:** Python 3.13+
- **Web Framework:** FastAPI
- **Server:** Uvicorn
- **Package Manager:** uv
- **AI/LLM Framework:** LangChain (`langchain.agents.create_agent`), LangGraph
- **Memory/Vector DB:** Mem0, Qdrant, MongoDB
- **Validation:** Pydantic V2
- **Testing:** Pytest
- **Realtime Communication:** WebSockets

## STRUCTURE

```
backend/
├── src/
│   ├── api/routes/        # 6 FastAPI routers (stm, ltm, tts, websocket, slack, callback)
│   ├── configs/           # Pydantic settings + YAML loader (agent/, ltm/, tts/)
│   ├── core/              # logger.py (Loguru + request ID), middleware.py
│   ├── models/            # Pydantic V2 schemas per domain
│   ├── services/          # 7 services — see src/services/CLAUDE.md
│   └── main.py            # App factory (create_app → get_app), lifespan, service init
├── tests/                 # Mirrors src/ — see tests/CLAUDE.md
├── docs/                  # API specs, WS protocol, data flows — see docs/CLAUDE.md
├── scripts/               # run.sh, e2e.sh, lint.sh, verify.sh, clean/
├── yaml_files/            # Runtime config (personas.yml, tts_rules.yml, services/*.yml)
├── worktrees/             # Git worktrees for feature isolation (auto-generated, ignore)
└── examples/              # Demo scripts (WS client, TTS streaming)
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add API route | `src/api/routes/` + `src/models/` | Include router in `src/api/routes/__init__.py` |
| Add service | `src/services/<name>/` | Init in `service_manager.py`, register in `main.py` lifespan |
| Modify agent | `src/services/agent_service/` | See `agent_service/CLAUDE.md` |
| Add agent tool | `src/services/agent_service/tools/` | Follow existing tool pattern |
| Add agent middleware | `src/services/agent_service/middleware/` | `before_model` hook pattern (see `task_status_middleware.py`) |
| Change TTS | `src/services/tts_service/` | See `tts_service/CLAUDE.md` |
| WebSocket protocol | `src/services/websocket_service/` | See `websocket_service/AGENTS.md` + `docs/websocket/CLAUDE.md` |
| Add env variable | `src/configs/settings.py` | Document in `docs/setup/ENVIRONMENT.md` |
| Add YAML config | `yaml_files/` | **Unified**: `services.yml` (local), `services.docker.yml`, `services.e2e.yml` |
| Slack integration | `src/services/channel_service/` | See `channel_service/CLAUDE.md` |
| MongoDB repository | `src/services/<name>/` | Follow `pending_task_repository.py` pattern (TTL index, async CRUD) |

## COMPLEXITY HOTSPOTS

| File | Lines | Concern |
|------|-------|---------|
| `services/websocket_service/message_processor/processor.py` | 626 | Turn lifecycle, async task coordination |
| `services/service_manager.py` | 652 | Singleton init, async/sync bridging, YAML config loading |
| `services/websocket_service/message_processor/event_handlers.py` | 448 | Agent event → TTS chunk pipeline |
| `services/websocket_service/manager/websocket_manager.py` | 455 | Connection lifecycle, heartbeat |
| `services/websocket_service/manager/handlers.py` | 393 | Message routing, chat turn management |

## CONTEXT-SENSITIVE DOCS

| Path | Content |
|------|---------|
| `src/CLAUDE.md` | Logging (format, levels, request ID) |
| `tests/CLAUDE.md` | Testing (pytest, fixtures, structural tests) |
| `docs/CLAUDE.md` | Doc authoring (200-line rule, structure) |
| `docs/websocket/CLAUDE.md` | WebSocket protocol (message types, lifecycle) |
| `src/services/tts_service/CLAUDE.md` | TTS (EmotionMotionMapper, synthesize_chunk) |
| `src/services/agent_service/CLAUDE.md` | Agent (LangGraph, middleware, memory) |
| `src/services/channel_service/CLAUDE.md` | Channel (Slack, session_lock, reply_channel) |
| `src/services/AGENTS.md` | Service layer (init order, deps, patterns) |
| `src/services/websocket_service/AGENTS.md` | WebSocket internals (processor, manager) |

## CONVENTIONS

- **Async-first**: All I/O uses `async/await`. No sync DB/API calls.
- **Type hints**: Strict. `|` for unions (3.10+ style). No `Any`.
- **No print()**: Always `loguru.logger`. See `src/CLAUDE.md`.
- **No hardcoded config**: Use `settings` object or YAML injection.
- **Factory pattern**: `create_app()` → `get_app()` for uvicorn.
- **Service singletons**: Module-level lazy init via `service_manager.py`.
- **Pydantic V2**: All request/response models. Validators, not manual checks.
- **Request ID**: Bound at middleware, threaded through all logs.

## ARCHITECTURAL PATTERNS (PR #26-#30)

### MongoDB Repository Pattern
- Async CRUD with Motor driver, TTL index for auto-cleanup
- Follow `pending_task_repository.py` pattern: `find_by_id`, `insert`, `update_status`, `find_expirable`
- TTL index: `expireAfterSeconds=604800` (7 days)

### Agent Middleware Chain
- `before_model` hook: inject ephemeral context (task status, profile, summary) into system prompt
- Middleware order matters: ToolGate → Delegate → LTM → Profile → Summary → TaskStatus
- Never persist injected data to state — ephemeral only

### ToolGateMiddleware (Defense-in-Depth)
- Validates shell commands against whitelist + rejects metacharacters (`;|&\`$\n`)
- Filesystem: `Path.resolve()` + `relative_to()` for allowed-dir enforcement
- Fail-closed: `None` = inactive, `[]` = deny all
- Error messages never leak whitelist/paths

### Stateless MCP Client (langchain-mcp-adapters 0.2.2)
- No `__aenter__/__aexit__` — direct `await client.get_tools()`
- Graceful degradation: MCP failure → empty tools, no crash
- `cleanup_async()` no-op in shutdown

### Unified YAML Config
- 3 environment files: `services.yml` (local), `services.docker.yml`, `services.e2e.yml`
- Single `services_file` key in main config, not N service paths
- `YAML_FILE` env var override for custom configs

## ANTI-PATTERNS (THIS PROJECT)

- **Never** suppress types (`Any`, `type: ignore`).
- **Never** use `print()` — always `logger`.
- **Never** skip E2E tests — `bash scripts/e2e.sh` must pass before done.
- **Never** add DEBUG logs to production code paths.
- **Never** log sensitive data (passwords, tokens, PII).
- **Never** hardcode service URLs or credentials.
- **TDD mandatory**: RED → GREEN → REFACTOR. No exceptions.

## 3. Coding Conventions

### A. General Principles

- **Type Hinting:** Use strict type hints for all functions and variables. Use `|` for unions (Python 3.10+ style).
- **Asynchronous First:** Prefer `async/await` for all I/O operations (DB, API calls).
- **Dependency Injection:** Use FastAPI's `Depends` for route dependencies.
- **Configuration:** Do not hardcode settings. Use the central `settings` object or YAML config injection.

### B. Naming Conventions

- **Files/Modules:** `snake_case.py`
- **Classes:** `PascalCase`
- **Variables/Functions:** `snake_case`
- **Constants:** `UPPER_CASE`

### C. Setup

```bash
uv sync --all-extras        # install all dependencies
uv run pre-commit install   # install pre-commit hooks
```

### D. Makefile Targets

| Command | Description |
|---------|-------------|
| `make lint` | Run black + ruff + structural tests (`scripts/lint.sh`) |
| `make test` | Unit tests only (excludes e2e and slow markers) |
| `make e2e` | Full E2E test suite (`scripts/e2e.sh`) |
| `make fmt` | Auto-format with black + ruff fix |
| `make run` | Start FastAPI dev server (`scripts/run.sh`) |
| `make clean` | Remove `__pycache__`, `.pytest_cache`, `.pyc` artifacts |

See the [Testing Checklist](CHECKLIST.md) for detailed instructions and manual testing steps.
**YOU CAN'T SKIP E2E TESTS.** you must pass this test mark the task is done.
If the new feature cannot be tested with the existing E2E framework, you must first extend the E2E tests to cover it before marking the task as done.

### E. Dev Server

```bash
uv run uvicorn "src.main:get_app" --factory --port 5500 --reload

# For use slack, you need to run `ngrok http 5500`
# Override YAML config: YAML_FILE=yaml_files/custom.yml uv run uvicorn ...
```

## Task Tracking

- Tasks tracked in `TODO.md` with `cc:TODO` / `cc:WIP` / `cc:DONE` markers.

## Appendix

- [TODO](./TODO.md): Active task checklist (cc:TODO / cc:WIP / cc:DONE markers).
- [Golden Principles](./docs/GOLDEN_PRINCIPLES.md): 10 architectural invariants enforced by garden.sh.
- [Quality Score](./docs/QUALITY_SCORE.md): GP verification grade matrix.
- [Known Issues](./docs/known_issues/KNOWN_ISSUES.md): 기술 부채 추적.
- [Release Notes](./docs/release_notes/): 완료된 작업 이력 보관.
- [Scripts Reference](./docs/scripts-reference.md): scripts/clean/ 스크립트 레퍼런스.
