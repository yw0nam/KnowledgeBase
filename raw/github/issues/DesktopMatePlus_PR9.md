---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/9"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 9
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-03T14:36:39Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #9: fix(qa): resolve GP-4 hardcoded URLs and GP-3 bare print violations

## Summary

**QA-1 (GP-4 Critical) — Hardcoded URL removal:**
- `src/configs/settings.py`: added `backend_url` + `nanoclaw_url` fields to `Settings`, defaulting to `BACKEND_URL` / `NANOCLAW_URL` env vars
- `disconnect_handler.py`: replaced module-level `os.getenv("BACKEND_URL", ...)` with lazy `get_settings().backend_url`
- `delegate_task.py`: replaced module-level `NANOCLAW_URL` / `BACKEND_URL` constants with lazy `get_settings()` calls inside `_arun`
- `vllm_omni.py`: removed hardcoded `"http://127.0.0.1:5517"` default from `__init__` — `base_url` is now required (factory always passes it from YAML)
- `tts_factory.py` + `agent_factory.py`: `__main__` example blocks now load URLs from their respective YAML configs instead of hardcoding

**QA-2 (GP-3 Major) — Bare print removal:**
- `main.py`, `ltm_factory.py`, `vllm_omni.py`, `tts_factory.py`, `agent_factory.py`, `message_util.py`, `text_processor.py` — all `print()` calls replaced with `logger.info/warning/error/exception/debug`

**Structural tests:** cleared `_KNOWN_PRINT_FILES` and `_KNOWN_LOCALHOST_FILES` known-debt sets in `tests/structural/test_architecture.py`

## Test Coverage

All new code paths are config/logging wiring — no new business logic. Structural tests (9/9 pass) validate GP-3 and GP-4 compliance via AST analysis.

## Pre-Landing Review

No issues found. All changes are mechanical replacements with no new logic.

## Design Review

No frontend files changed — design review skipped.

## Note on e2e.sh

`bash backend/scripts/e2e.sh` fails due to pre-existing LLM API errors (`System message must be at the beginning`) unrelated to this PR. The same failures exist on `master` before this change. Confirmed by running e2e on master: identical failure pattern.

## Test plan
- [x] `sh scripts/lint.sh` — 9/9 structural tests pass, ruff + black clean
- [x] `grep -rn 'print(' src/` → GP-3: CLEAN
- [x] `grep -rn 'localhost\|127\.0\.0\.1' src/ | grep -v config | grep -v test` → GP-4: CLEAN

🤖 Generated with [Claude Code](https://claude.com/claude-code)
