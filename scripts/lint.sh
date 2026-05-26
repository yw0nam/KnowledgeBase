#!/usr/bin/env bash
set -e

# Format (mutating)
uv run black src/ test/
uv run ruff check src/ test/ --unsafe-fixes --fix

# Verify (non-mutating)
uv run python -m kb.cli.lint_wiki
uv run python -m kb.cli.lint_handoff

# Frontend (only when present and installed).
if [ -d frontend ] && [ -d frontend/node_modules ]; then
  (cd frontend && npm run format -- --log-level warn)
  (cd frontend && npm run lint)
  (cd frontend && npm run typecheck)
fi
