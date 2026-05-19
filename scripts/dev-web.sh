#!/usr/bin/env bash
# Start the kb-web FastAPI service and the Vite dev server together.
#
# Both processes are foregrounded with their output prefixed so a
# single Ctrl-C cleans up cleanly. Optional env:
#
#   KB_DATA_DIR   Path to the local data tree (default: <repo>/data)
#   KB_WEB_PORT   FastAPI port (default 8765)
#   VITE_PORT     Vite port (default 5173)

set -e

cd "$(dirname "$0")/.."

if [ ! -d frontend/node_modules ]; then
  echo "frontend/node_modules missing — running npm install first..."
  (cd frontend && npm install)
fi

API_PORT="${KB_WEB_PORT:-8765}"
VITE_PORT="${VITE_PORT:-5173}"

echo "kb-web   → http://127.0.0.1:${API_PORT}"
echo "vite     → http://127.0.0.1:${VITE_PORT}"
if [ -n "${KB_DATA_DIR:-}" ]; then
  echo "data dir → ${KB_DATA_DIR}"
else
  echo "data dir → <repo>/data (override with KB_DATA_DIR)"
fi
echo

pids=()

cleanup() {
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

KB_WEB_PORT="$API_PORT" uv run kb-web --reload --port "$API_PORT" \
  2>&1 | sed -u 's/^/[api]  /' &
pids+=($!)

(cd frontend && KB_WEB_PORT="$API_PORT" npm run dev -- --port "$VITE_PORT") \
  2>&1 | sed -u 's/^/[vite] /' &
pids+=($!)

wait
