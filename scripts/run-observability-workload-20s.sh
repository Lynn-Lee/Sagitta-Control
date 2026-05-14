#!/usr/bin/env sh
set -eu

LOG_FILE="${OBS_WORKLOAD_LOG:-/opt/sagittadb/source/logs/observability_workload.log}"
CONTAINER="${OBS_WORKLOAD_CONTAINER:-sagittadb-source-test-backend-1}"

mkdir -p "$(dirname "$LOG_FILE")"

run_once() {
  /usr/bin/docker exec -w /app -e PYTHONPATH=/app "$CONTAINER" \
    python scripts/observability_workload.py >> "$LOG_FILE" 2>&1
}

sleep_until() {
  target="$1"
  now="$(date +%s)"
  if [ "$target" -gt "$now" ]; then
    sleep "$((target - now))"
  fi
}

start="$(date +%s)"
run_once
sleep_until "$((start + 20))"
run_once
sleep_until "$((start + 40))"
run_once
