---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/30"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 30
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-13T06:58:22Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #30: refactor: decouple pending_tasks from LangGraph to MongoDB (KI-17)

## Summary

- **KI-17 해결**: `pending_tasks`를 LangGraph checkpointer state에서 별도 MongoDB 컬렉션으로 완전 분리
- Synthetic SystemMessage 주입 제거 → before_model middleware로 대체 (ephemeral injection)
- Sweep service O(N) session iteration → 단일 MongoDB query로 최적화
- E2E에서 `FASTAPI_URL` 환경변수 누락 수정

### 변경 파일 (21 files, -197 lines net)

| Component | Change |
|-----------|--------|
| `pending_task_repository.py` (NEW) | MongoDB CRUD + TTL index (7-day auto-cleanup) |
| `task_status_middleware.py` (NEW) | before_model hook — running/recent tasks → system prompt inject |
| `callback.py` | `aget_state`/`aupdate_state` 완전 제거, MongoDB 직접 접근 |
| `sweep.py` | O(N) session iteration → 단일 `find_expirable` query |
| `delegate_task.py` | `Command(update={"pending_tasks"})` → `repo.insert()` |
| `state.py` | `pending_tasks`, `PendingTask`, `ReplyChannel` 제거 |
| `stm.py` | `_ALLOWED_METADATA_KEYS`에서 제거 |
| `service_manager.py` | repo 등록 + `initialize_sweep_service` 시그니처 변경 |
| `main.py` | sweep init을 `pending_task_repo` 기반으로 변경 |
| `e2e.sh` | `FASTAPI_URL` export 추가 |

### ADR

- **Decision**: MongoDB collection + middleware injection
- **Why**: State hygiene (no synthetic messages), sweep efficiency (O(1)), separation of concerns
- **Tradeoff**: Task results are ephemeral (system prompt only) — LTM absorbs long-term

## Test plan

- [x] `make lint` — ruff + black + structural tests (23 passed)
- [x] `make test` — 606 passed, 0 failed
- [x] `make e2e` — Phase 1-5 OK (health check timeout in `test_misc_e2e.py` is pre-existing, separate fix)
- [ ] Manual smoke test: delegate task via WebSocket → verify MongoDB document + middleware injection

🤖 Generated with [Claude Code](https://claude.com/claude-code)
