#!/usr/bin/env bash
# Repeated controlled comparison of the core stack, GoFlow2 under synthetic load,
# and Snitch socket snapshots. Runs only on the Docker engine used by bench_stack.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname -- "$SCRIPT_DIR")"
cd "$REPO_ROOT"

DURATION="${DURATION:-900}"
INTERVAL="${INTERVAL:-10}"
REPEATS="${REPEATS:-3}"
RATE="${RATE:-10}"
SNITCH_TEST_PORT="${SNITCH_TEST_PORT:-5080}"
OUT_ROOT="$REPO_ROOT/.artifacts/bench/network-eval"
PROBE_COUNT=$((DURATION * RATE))

mkdir -p "$OUT_ROOT"

restore_services() {
  docker compose --profile netflow --profile network-inspect \
    start goflow2 snitch >/dev/null 2>&1 || true
}
trap restore_services EXIT INT TERM

run_bench() {
  local phase="$1"
  local repeat="$2"
  local log_path="$OUT_ROOT/rep${repeat}-${phase}-harness.log"

  echo "==> rep${repeat} ${phase} (${DURATION}s, ${INTERVAL}s interval)" >&2
  if ! mise exec uv -- uv run python tools/bench_stack.py \
    --scenario idle --duration "$DURATION" --interval "$INTERVAL" \
    --no-fail-on-budget \
    >"$log_path" 2>&1; then
    cat "$log_path" >&2
    return 1
  fi
  cat "$log_path" >&2

  local run_dir
  run_dir="$(sed -n 's/^Artifacts: \(.*\)$/\1/p' "$log_path" | tail -n 1)"
  if [[ -z "$run_dir" || ! -d "$run_dir" ]]; then
    echo "ERROR: benchmark harness did not report an artifact directory" >&2
    return 1
  fi

  local run_id
  run_id="$(basename "$run_dir")"
  cp -r "$run_dir" "$OUT_ROOT/rep${repeat}-${phase}-${run_id}"
  printf '%s\n' "$run_id"
}

run_compare() {
  local baseline="$1"
  local current="$2"
  local label="$3"
  local repeat="$4"
  local log_path="$OUT_ROOT/rep${repeat}-${label}-compare.log"

  if ! mise exec uv -- uv run python tools/bench_compare.py \
    "$baseline" "$current" >"$log_path" 2>&1; then
    cat "$log_path" >&2
    return 1
  fi
  cat "$log_path" >&2
}

for repeat in $(seq 1 "$REPEATS"); do
  echo "########## network evaluation repeat ${repeat}/${REPEATS} ##########"

  docker compose stop goflow2 snitch
  sleep 10
  baseline_run="$(run_bench baseline "$repeat")"

  docker compose --profile netflow start goflow2
  sleep 5
  flow_before=0
  if [[ -f .data/goflow2/flows.jsonl ]]; then
    flow_before="$(wc -l < .data/goflow2/flows.jsonl)"
  fi

  python3 tools/netflow_probe.py --count "$PROBE_COUNT" --rate "$RATE" &
  probe_pid="$!"
  set +e
  goflow_run="$(run_bench goflow "$repeat")"
  bench_status="$?"
  wait "$probe_pid"
  set -e
  if [[ "$bench_status" -ne 0 ]]; then
    exit "$bench_status"
  fi

  flow_after="$(wc -l < .data/goflow2/flows.jsonl)"
  flow_delta=$((flow_after - flow_before))
  echo "==> GoFlow2 functional result: offered=${PROBE_COUNT} decoded=${flow_delta}"

  docker compose stop goflow2
  docker compose --profile network-inspect start snitch
  sleep 5

  python3 -c \
    "import socket, time; s=socket.socket(); s.connect(('127.0.0.1', ${SNITCH_TEST_PORT})); time.sleep(${DURATION})" &
  hold_pid="$!"
  sleep 5
  echo "==> Snitch attribution sample:"
  docker exec localobserve-snitch-1 /usr/local/bin/snitch ls \
    --resolve-addrs=false proc=python3 -p
  set +e
  snitch_run="$(run_bench snitch "$repeat")"
  bench_status="$?"
  wait "$hold_pid"
  set -e
  if [[ "$bench_status" -ne 0 ]]; then
    exit "$bench_status"
  fi

  echo "==> rep${repeat} GoFlow2 vs baseline:"
  run_compare "$baseline_run" "$goflow_run" goflow "$repeat"
  echo "==> rep${repeat} Snitch vs baseline:"
  run_compare "$baseline_run" "$snitch_run" snitch "$repeat"

  sleep 30
done

echo "All network evaluation repeats complete. Artifacts: $OUT_ROOT"
