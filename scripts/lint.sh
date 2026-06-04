#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load host environment (DATABASE_URL) so kb-lint reaches Postgres.
set -a
# shellcheck disable=SC1091
[ -f "$KB_ROOT/.env" ] && . "$KB_ROOT/.env"
set +a

# Format (mutating)
uv run black src/ test/
uv run ruff check src/ test/ --unsafe-fixes --fix

# Verify (non-mutating)
uv run kb-lint all
