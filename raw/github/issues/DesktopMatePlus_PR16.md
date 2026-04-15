---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/16"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 16
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-09T02:58:47Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #16: fix: persona SystemMessage이 신규 세션에서 누락되는 버그 수정

## 문제

`handlers.py`에서 `session_id=None`(신규 세션)을 `str(uuid4())`로 변환한 **이후**에 `agent_service.stream()`을 호출하므로, `OpenAIChatAgent.stream/invoke`의 기존 조건 `if persona_text and not session_id:`가 항상 `False`가 되어 persona SystemMessage가 절대 주입되지 않았다.

## 수정 내용

- `AgentService.stream()` / `invoke()` 추상 메서드에 `is_new_session: bool = False` 파라미터 추가 (`service.py`)
- `OpenAIChatAgent.stream()` / `invoke()`의 persona 주입 조건을 `not session_id` → `is_new_session`으로 변경 (`openai_chat_agent.py`)
- `handlers.py`에서 UUID 생성 **전에** `is_new_session = session_id is None` 캡처 후 `stream()` 호출 시 전달
- `channel_service/__init__.py`의 `invoke()` 호출은 session_id가 항상 외부에서 주어지므로 기본값 `False` 유지 (안전)
- `docs/known_issues/KNOWN_ISSUES.md`에 KI-2 (파일 크기 초과 기술 부채) 추가

## 테스트 계획

- [x] `tests/agents/test_persona_injection.py` 신규 추가 — `is_new_session=True/False` + unknown persona_id 각 케이스 (stream/invoke 각 3개, 총 6개)
- [x] 기존 `tests/agents/test_openai_chat_agent.py` 페르소나 관련 테스트 업데이트 (`session_id=""` → `is_new_session=True`)
- [x] `uv run pytest tests/agents/test_persona_injection.py tests/agents/test_openai_chat_agent.py` → 13 passed
- [x] `sh scripts/lint.sh` → All checks passed (ruff + black + 9 structural tests)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
