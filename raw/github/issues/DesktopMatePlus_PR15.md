---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/15"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 15
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-08T03:07:32Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #15: refactor: standalone 전환 및 OMC 워크플로우 정렬

## Summary

- 크로스레포 참조 제거 — nanoclaw, desktop-homunculus, Director-Artisan 패턴 의존성 완전 분리
- 태스크 트래킹 전환 — `Plans.md` → `TODO.md` (cc:TODO / cc:WIP / cc:DONE)
- `AGENTS.md` OMC 네이티브 정렬 — executor, code-reviewer, security-reviewer 등 subagent_type 기반으로 전면 교체, TDD 필수화
- Golden Principles backend-only 재정렬 — GP-5(Delegation), GP-6(NanoClaw), GP-13(DH MOD) 제거 → 10개로 축소
- `scripts/clean/` 추가 — garden.sh, check_docs.sh, babysit-collect.sh 등 6개 + run-quality-agent.sh 신규 생성
- `quality-agent` worktree 격리 — `git worktree add` 기반으로 전환, PR 생성 후 자동 cleanup

## Test plan

- [ ] `sh scripts/lint.sh` 통과 확인
- [ ] `bash -n scripts/clean/garden.sh` 구문 검사
- [ ] AGENTS.md에 Plans.md / Director / /review / /cso 잔재 없음 확인

🤖 Generated with [Claude Code](https://claude.com/claude-code)
