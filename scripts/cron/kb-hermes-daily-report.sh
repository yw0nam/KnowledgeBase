#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KB_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TARGET="${1:-$(TZ="${KB_TZ:-Asia/Seoul}" date -d 'yesterday' +%F)}"

cd "$KB_ROOT" || exit 1
uv run kb-hermes-daily-report --date "$TARGET" --lint
