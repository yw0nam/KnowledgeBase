#!/usr/bin/env bash
set -euo pipefail

cd /home/spow12/codes/KnowledgeBase
TARGET="${1:-$(TZ=Asia/Seoul date -d 'yesterday' +%F)}"
YYYY="${TARGET:0:4}"
MM="${TARGET:5:2}"

uv run kb-usage-daily-report --date "$TARGET" --lint