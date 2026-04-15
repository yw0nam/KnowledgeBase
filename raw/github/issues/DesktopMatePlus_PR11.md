---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/11"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 11
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-04T07:12:17Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #11: feat: add POST /v1/tts/speak endpoint

## Summary

- **New endpoint** `POST /v1/tts/speak` in `src/api/routes/tts.py` — accepts `{ "text": "..." }`, returns `{ "audio_base64": "..." }` as WAV audio in base64 encoding
- **New Pydantic models** `SpeakRequest` / `SpeakResponse` in `src/models/tts.py`
- Delegates to `TTSService.generate_speech()` via `asyncio.to_thread` (correct async wrapping of blocking I/O)
- Returns 503 if service unavailable, not initialized, or synthesis fails (including `None` and `False` return values)

## Test Coverage

All 7 new code paths tested:
- 200 happy path with audio_base64
- generate_speech called with correct args (base64, wav)
- 503 when service is None
- 503 when generate_speech returns None
- 503 when generate_speech returns False (edge case — non-str guard via `isinstance`)
- 422 when text missing
- 422 when body missing

Tests: 0 → 1 new file (+7 tests)

## Pre-Landing Review

Pre-Landing Review: 1 informational auto-fixed
- `[AUTO-FIXED] src/api/routes/tts.py:56` — Changed `is None` guard to `isinstance(audio_base64, str)` to cleanly reject `None`, `False`, or `bytes` return values from `generate_speech`

## Design Review

No frontend files changed — design review skipped.

## Eval Results

No prompt-related files changed — evals skipped.

## Greptile Review

No Greptile comments.

## Plan Completion

- [DONE] `POST /v1/tts/speak` endpoint — `src/api/routes/tts.py` (+36 lines)
- [DONE] Request/response Pydantic models — `src/models/tts.py` (+14 lines)
- [DONE] Pytest TDD — `tests/api/test_tts_speak_api.py` (+72 lines, 7 tests)

COMPLETION: 3/3 DONE

## TODOS

No TODO items completed in this PR.

## Test plan
- [x] i already confirm E2E test is passed (pre-existing failures in Phase 4/5 are unrelated to TTS — agent LLM "System message must be at the beginning" error pre-dates this branch)
- [x] 7 new TTS speak tests pass
- [x] Existing 5 TTS voices tests pass
- [x] lint.sh clean (ruff + black + structural tests)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
