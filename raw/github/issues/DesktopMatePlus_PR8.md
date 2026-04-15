---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/8"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 8
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-01T12:08:15Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #8: docs: sync v2.4.0 documentation (IrodoriTTS + emoji emotion)

## Summary

Post-ship documentation sync for v2.4.0 (BE-FEAT-1 + BE-FEAT-2). Code changes already landed via PR #7.

**Documentation updates:**
- **README.md**: replaced Fish Speech with IrodoriTTS in features list, project structure, external APIs, and dependencies link
- **CHANGELOG.md**: added v2.4.0 entry — IrodoriTTSService, emoji emotion detection, Fish Speech removal
- **CLAUDE.md**: added `yaml_files/services/tts_service/irodori.yml` reference; updated `tts_rules.yml` description to reflect emoji detection
- **EMOJI_ANNOTATIONS.md**: committed bilingual emoji-to-emotion reference table (45 emojis) for IrodoriTTS voice control

## Test Coverage
All new code paths have test coverage — 412 passed, 11 skipped (100% coverage on new paths).

## Pre-Landing Review
No issues found (docs-only changes, code already reviewed in PR #7).

## Adversarial Review
Docs-only diff — adversarial review not applicable.

## Plan Completion
No plan file — skipping.

## TODOS
No TODO items in this repo. Project uses Plans.md.

## Test plan
- [x] All pytest tests pass (412 passed, 0 failures)
- [x] Documentation factually accurate against diff

🤖 Generated with [Claude Code](https://claude.com/claude-code)
