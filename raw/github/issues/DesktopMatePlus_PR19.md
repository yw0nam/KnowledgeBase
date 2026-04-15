---
source_url: "https://github.com/yw0nam/DesktopMatePlus/pull/19"
type: github_pr
repo: "yw0nam/DesktopMatePlus"
pr_number: 19
state: "MERGED"
labels: ""
captured_at: "2026-04-15T00:43:20Z"
created_at: "2026-04-10T02:04:09Z"
author: "yw0nam"
contributor: "nam-young-woo"
tags: [pr]
---

# PR #19: feat: add Makefile, Dockerfile, and docker-compose (DevEx)

## Summary

- Add `Makefile` with `lint`, `test`, `e2e`, `run`, `fmt`, `clean` targets wrapping existing scripts
- Add `Dockerfile` using Python 3.13-slim + uv, exposes port 5500
- Add `docker-compose.yml` with backend + MongoDB 7 + Qdrant services (health checks + named volumes)
- Add `tests/structural/test_devex_files.py` with 14 structural tests verifying file presence and required structure

TTS is external — excluded from compose intentionally.

## Test plan

- [x] `uv run pytest tests/structural/test_devex_files.py` → 14 passed
- [x] `sh scripts/lint.sh` → black + ruff + 23 structural tests all passed
- [ ] `docker compose up` (requires Docker daemon — manual verification)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
