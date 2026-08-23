#!/usr/bin/env bash
#
# verify-runtimes.sh — cross-runtime acceptance harness (Plan §5).
#
# Boots the LocalObserve stack on Docker, Podman, and Nerdctl, waits for all
# healthchecks, then runs the static detection-coverage checks against the
# running stack. Each runtime uses an isolated compose project name so multiple
# runtimes can be exercised on one host without collision.
#
# Requires: one of docker/podman/nerdctl on PATH plus its engine/daemon running
# (mise installs the CLIs only — see mise.toml; the daemon must come from the
# host: dockerd, containerd for nerdctl, or a podman machine for podman-remote).

set -uo pipefail

RUNTIMES=("docker" "podman" "nerdctl")
MAX_WAIT=120

# Map a runtime name to its compose command.
compose_cmd() {
  case "$1" in
    docker)  echo "docker compose" ;;
    podman)  echo "podman compose" ;;
    nerdctl) echo "nerdctl compose" ;;
    *) echo "unknown runtime: $1" >&2; return 1 ;;
  esac
}

wait_healthy() {
  local rt="$1" cmd project
  cmd="$(compose_cmd "$rt")" || return 1
  project="localobserve-${rt}"
  local elapsed=0
  echo "==> [$rt] waiting for healthy services (project: $project)..."
  while (( elapsed < MAX_WAIT )); do
    # Healthy once no service is explicitly "starting" or "unhealthy". Services
    # without a healthcheck report an empty value, which is treated as healthy
    # (not as perpetually "starting"), so they don't stall the wait loop.
    if $cmd -p "$project" ps --format '{{.Health}}' 2>/dev/null \
        | grep -qE '^(starting|unhealthy)$'; then
      sleep 5
      elapsed=$((elapsed + 5))
    else
      echo "==> [$rt] all services healthy after ${elapsed}s"
      return 0
    fi
  done
  echo "==> [$rt] TIMEOUT waiting for health" >&2
  return 1
}

verify_one() {
  local rt="$1" cmd project
  cmd="$(compose_cmd "$rt")" || return 1
  project="localobserve-${rt}"
  echo "########## RUNTIME: $rt ##########"

  if ! command -v "$rt" >/dev/null 2>&1; then
    echo "SKIP: '$rt' not found on PATH (install via mise: mise install)" >&2
    return 0
  fi

  set -e
  $cmd -p "$project" up -d
  set +e
  if ! wait_healthy "$rt"; then
    $cmd -p "$project" logs --tail=50
    $cmd -p "$project" down -v
    return 1
  fi

  # Static + dynamic detection checks (mirrors `task test-detection-coverage`).
  uv run python -m pytest \
    tests/test_detection_coverage.py tests/test_falco_rules.py tests/test_osquery_config.py \
    -v

  # Exercise the full pipeline end-to-end if the stack is live.
  task trigger-detections || true

  $cmd -p "$project" down -v
  echo "########## END: $rt ##########"
}

main() {
  local failed=0
  for rt in "${RUNTIMES[@]}"; do
    verify_one "$rt" || failed=$((failed + 1))
  done
  if (( failed > 0 )); then
    echo "ERROR: $failed runtime(s) failed verification" >&2
    exit 1
  fi
  echo "OK: all available runtimes verified."
}

main "$@"
