#!/usr/bin/env bash

# Load host environment (DATABASE_URL, KB_API_URL, KB_API_TOKEN) when present.
# Sourced by every cron wrapper after KB_ROOT is set.

# Hermes cron may run with a minimal PATH and a profile-scoped HOME
# (for example /home/spow12/.hermes/home). Resolve the operator home from
# passwd data first so user-local tools are found consistently.
CRON_OPERATOR_USER="${LOGNAME:-${USER:-spow12}}"
CRON_OPERATOR_HOME="${CRON_OPERATOR_HOME:-$(getent passwd "$CRON_OPERATOR_USER" 2>/dev/null | cut -d: -f6)}"
CRON_OPERATOR_HOME="${CRON_OPERATOR_HOME:-/home/spow12}"

# opencode and other user tools read config/credentials from HOME. Hermes cron
# can provide a profile-scoped HOME, so normalize it for project cron children.
export HOME="$CRON_OPERATOR_HOME"

# Keep all wrappers able to find uv, opencode, psql, and user-local shims
# without relying on an interactive shell.
export PATH="$CRON_OPERATOR_HOME/.opencode/bin:$CRON_OPERATOR_HOME/.local/bin:$CRON_OPERATOR_HOME/anaconda3/bin:$CRON_OPERATOR_HOME/.bun/bin:$CRON_OPERATOR_HOME/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

# Use explicit binary paths so nested non-interactive cron shells do not depend on
# login-shell startup files. Allow overrides for fresh hosts or tests.
export UV_BIN="${UV_BIN:-$CRON_OPERATOR_HOME/anaconda3/bin/uv}"
export OPENCODE_BIN="${OPENCODE_BIN:-$CRON_OPERATOR_HOME/.opencode/bin/opencode}"
export KB_OPENCODE_MODEL="${KB_OPENCODE_MODEL:-anthropic/claude-sonnet-4-6}"

if [[ -n "${KB_ROOT:-}" && -f "$KB_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$KB_ROOT/.env"
  set +a
fi

kb_finish_cron_run() {
  local job_name="$1"
  local target="$2"
  local run_exit="$3"
  local log_file="$4"
  local status="success"
  local submit_exit=0
  local log_path=""
  local args=()

  if [[ "$run_exit" -ne 0 ]]; then
    status="failed"
  fi

  if [[ "$log_file" == "$KB_ROOT/data/"* ]]; then
    log_path="${log_file#"$KB_ROOT/data/"}"
  fi

  args=(
    --job-name "$job_name"
    --target "$target"
    --status "$status"
    --exit-code "$run_exit"
    --log-file "$log_file"
  )
  if [[ -n "$log_path" ]]; then
    args+=(--log-path "$log_path")
  fi

  (
    cd "$KB_ROOT"
    env -u VIRTUAL_ENV "$UV_BIN" run kb-submit-cron-run "${args[@]}"
  ) || submit_exit=$?

  if [[ "$run_exit" -ne 0 ]]; then
    return "$run_exit"
  fi
  return "$submit_exit"
}
