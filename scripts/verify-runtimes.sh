#!/usr/bin/env bash
#
# verify-runtimes.sh — cross-runtime acceptance harness (Plan §5).
#
# Boots the LocalObserve stack on Docker, Podman, and Nerdctl, waits for all
# healthchecks, then runs detection checks against the running stack. Each
# runtime uses an isolated compose project name so multiple runtimes can be
# exercised on one host without collision.
#
# Requires: one of docker/podman/nerdctl on PATH plus its engine/daemon running
# (mise installs the CLIs only — see mise.toml; the daemon must come from the
# host: dockerd, containerd for nerdctl, or a podman machine for podman-remote).

set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=runtime-compose.sh
source "${SCRIPT_DIR}/runtime-compose.sh"

RUNTIMES=("docker" "podman" "nerdctl")
MAX_WAIT="${MAX_WAIT:-120}"

# The compose file publishes these ports for local access. Project names isolate
# engine objects but cannot isolate host port bindings, so fail closed with a
# clear SKIP when another stack already owns one of them.
REQUIRED_TCP_PORTS=(5080 5081 4317 4318 9000 9090)
REQUIRED_UDP_PORTS=(2055 6343)

host_port_in_use() {
  local protocol="$1"
  local port="$2"
  command -v ss >/dev/null 2>&1 || return 1
  ss -H -l"$protocol" 2>/dev/null \
    | awk '{print $4}' \
    | grep -qE "(:|\\.)${port}$"
}

host_ports_available() {
  local protocol port
  local conflicts=()
  for port in "${REQUIRED_TCP_PORTS[@]}"; do
    if host_port_in_use t "$port"; then
      conflicts+=("tcp:${port}")
    fi
  done
  for port in "${REQUIRED_UDP_PORTS[@]}"; do
    if host_port_in_use u "$port"; then
      conflicts+=("udp:${port}")
    fi
  done

  if (( ${#conflicts[@]} > 0 )); then
    echo "SKIP: required host ports are already in use: ${conflicts[*]}" >&2
    echo "      stop the conflicting stack/process before running cross-runtime acceptance" >&2
    return 1
  fi
  return 0
}

wait_healthy() {
  local rt="$1"
  local elapsed=0
  local status
  echo "==> [$rt] waiting for running/healthy services (project: ${COMPOSE_PROJECT_NAME})..."

  while (( elapsed < MAX_WAIT )); do
    # Compose implementations report an empty health field for services that
    # have no healthcheck. Those services are acceptable once their state is
    # running; only an explicitly non-running state should keep waiting.
    if ! status="$(runtime_compose "$rt" ps --format '{{.State}} {{.Health}}' 2>/dev/null)"; then
      status=""
    fi

    if [[ -z "${status//[[:space:]]/}" ]]; then
      sleep 5
      elapsed=$((elapsed + 5))
      continue
    fi

    if grep -qE '(^|[[:space:]])(starting|unhealthy|created|restarting|exited|dead|paused)([[:space:]]|$)' <<<"$status"; then
      sleep 5
      elapsed=$((elapsed + 5))
      continue
    fi

    echo "==> [$rt] all services running/healthy after ${elapsed}s"
    return 0
  done

  echo "==> [$rt] TIMEOUT waiting for health" >&2
  return 1
}

verify_one() (
  local rt="$1"
  local project="localobserve-${rt}"
  local started=0
  local binary
  COMPOSE_PROJECT_NAME="$project"

  cleanup() {
    if (( started )); then
      runtime_compose "$rt" down -v >/dev/null 2>&1 || true
    fi
  }
  trap cleanup EXIT INT TERM

  echo "########## RUNTIME: $rt ##########"

  if ! binary="$(runtime_binary "$rt" 2>/dev/null)"; then
    echo "SKIP: '$rt' CLI not found on PATH (install via mise: mise install)" >&2
    exit 0
  fi

  # A mise-installed client is not proof that its engine is available. Treat a
  # missing host daemon/machine as a blocked acceptance check, not a compose
  # regression, per AGENTS.md.
  if ! runtime_engine_available "$rt"; then
    echo "SKIP: '$binary' is installed but its engine is unavailable; start the host engine" >&2
    exit 0
  fi

  if ! runtime_compose "$rt" version >/dev/null 2>&1; then
    echo "ERROR: $rt Compose provider is unavailable or failed its version check" >&2
    exit 1
  fi

  if ! host_ports_available; then
    exit 0
  fi

  # Mark the stack as started before `up`: Compose can partially create services
  # before returning an error, and the EXIT trap must still clean those up.
  started=1
  if ! runtime_compose "$rt" up -d; then
    echo "ERROR: $rt failed to start the stack" >&2
    runtime_compose "$rt" logs --tail=50 || true
    exit 1
  fi

  if ! wait_healthy "$rt"; then
    runtime_compose "$rt" ps || true
    runtime_compose "$rt" logs --tail=50 || true
    exit 1
  fi

  # Static + dynamic detection checks (mirrors `task test-detection-coverage`).
  if ! uv run python -m pytest \
    tests/test_detection_coverage.py tests/test_falco_rules.py tests/test_osquery_config.py \
    -v; then
    echo "ERROR: static detection checks failed for $rt" >&2
    exit 1
  fi

  # Run the same trigger suite against this runtime/project. Falco probe
  # limitations are represented as skips by the trigger script; actual trigger
  # or webhook failures remain failures of this acceptance run.
  if ! RUNTIME="$rt" COMPOSE_PROJECT_NAME="$project" \
    bash "${SCRIPT_DIR}/../tools/trigger-detections.sh"; then
    echo "ERROR: detection trigger checks failed for $rt" >&2
    exit 1
  fi

  echo "########## END: $rt ##########"
)

main() {
  local failed=0
  for rt in "${RUNTIMES[@]}"; do
    verify_one "$rt" || failed=$((failed + 1))
  done
  if (( failed > 0 )); then
    echo "ERROR: $failed runtime(s) failed verification" >&2
    exit 1
  fi
  echo "OK: all available runtimes verified (missing engines were skipped)."
}

main "$@"
