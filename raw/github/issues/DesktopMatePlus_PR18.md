---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/18"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 18
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-09T11:44:55Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #18: fix: IrodoriTTS voice scan crash and test sync

## Summary
- **IrodoriTTS `_scan_voices()` crash**: `ref_audio_dir`가 `None`일 때 `AttributeError` 발생 → None guard 추가
- **irodori.yml 경로 오타**: `reference_voices` → `references_voices` (실제 디렉토리명과 불일치로 voices 로드 실패)
- **테스트 파일명 불일치**: 테스트가 `audio.wav`를 사용했으나 실제 리소스는 `merged_audio.mp3` → 테스트 수정
- **WebSocket 테스트 시그니처 불일치**: `FakeAgentService.stream()`에 `is_new_session` 파라미터 누락 → 추가

## Test plan
- [x] `uv run pytest` — 448 passed, 0 failed
- [x] 실서버에서 voices 로드 확인 완료

🤖 Generated with [Claude Code](https://claude.com/claude-code)
