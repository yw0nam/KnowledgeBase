---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/14"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 14
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-07T08:46:12Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #14: test: migrate e2e tests to pytest -m e2e infrastructure (BE-E1~E4)

## Summary

- **BE-E1**: `tests/e2e/` package with `conftest.py` — `require_backend` + `e2e_session` fixtures, `e2e` pytest marker registered in `pyproject.toml`
- **BE-E2**: `tests/e2e/test_websocket_e2e.py` — 5 tests covering WS lifecycle, stream token accumulation, stream_end content match, TTS chunk ordering/audio_base64 presence, 2-turn session continuity
- **BE-E3**: STM (`test_stm_e2e.py`, 4 tests), LTM (`test_ltm_e2e.py`, 3 tests, graceful skip on 503), misc health smoke (`test_misc_e2e.py`, 4 tests)
- **BE-E4**: `scripts/e2e.sh` Phase 4 replaced with `uv run pytest -m e2e --tb=long -v`; deleted `examples/test_stm.py`, `examples/test_ltm.py`, `examples/test_websocket.py`, `examples/multiturn_session_test.py`

## Test plan
- [ ] `uv run pytest -m e2e --collect-only` → 16 tests collected, no errors
- [ ] `bash -n scripts/e2e.sh` → syntax OK
- [ ] `uv run ruff check tests/e2e/` → clean
- [ ] Non-e2e suite: `uv run pytest tests/ --ignore=tests/e2e` → pre-existing 295 pass, 11 skip, 1 pre-existing failure unchanged
- [ ] With real backend: `FASTAPI_URL=http://localhost:5500 uv run pytest -m e2e --tb=long` → all pass

🤖 Generated with [Claude Code](https://claude.com/claude-code)
