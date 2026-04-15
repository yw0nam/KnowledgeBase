---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/10"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 10
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-03T17:09:34Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #10: fix: remove redundant {e} from logger.exception and use pathlib for YAML paths

## Summary

Post-merge sweep fix for PR #9 Gemini bot review comments (4 valid issues):

**logger.exception redundancy (`src/main.py`)**
- Line 207: `logger.exception(f"⚠️  Failed to initialize services: {e}")` → removed `{e}` and bare `except Exception as e:` → `except Exception:`
- Line 323: `logger.exception(f"⚠️  Failed to load configuration from ...: {e}")` → removed `{e}`, same pattern

`logger.exception()` automatically captures and appends the current exception (including traceback) — interpolating `{e}` duplicates it in the log output.

**Hardcoded relative YAML paths → pathlib**
- `src/services/agent_service/agent_factory.py`: `"./yaml_files/..."` → `Path(__file__).resolve().parents[3] / "yaml_files" / ...`
- `src/services/tts_service/tts_factory.py`: same pattern

`"./yaml_files/..."` resolves relative to CWD, not the source file's location. Using `pathlib.Path(__file__)` makes the path correct regardless of where the script is invoked from.

## Pre-Landing Review

No structural issues. Changes are purely mechanical — logging semantics and path resolution. No new logic.

## Test Coverage

All 9 structural tests pass (`sh scripts/lint.sh`). No new code paths — the `__main__` blocks are not exercised by the test suite (they are manual smoke test utilities only).

## Test plan
- [x] `sh scripts/lint.sh` — ruff + black clean, 9/9 structural tests pass
- [x] `git diff master...HEAD` — 3 files, 23 lines, no functional logic changes

🤖 Generated with [Claude Code](https://claude.com/claude-code)
