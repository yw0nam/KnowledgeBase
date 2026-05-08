#!/usr/bin/env bash
set -e

# Format (mutating)
uv run black src/ test/
uv run ruff check src/ test/ --unsafe-fixes --fix

# Verify (non-mutating)
uv run python -m kb_mcp.cli.lint_wiki
uv run python -m kb_mcp.cli.lint_handoff
