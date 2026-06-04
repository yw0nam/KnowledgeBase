#!/usr/bin/env bash

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
    uv run kb-submit-cron-run "${args[@]}"
  ) || submit_exit=$?

  if [[ "$run_exit" -ne 0 ]]; then
    return "$run_exit"
  fi
  return "$submit_exit"
}
