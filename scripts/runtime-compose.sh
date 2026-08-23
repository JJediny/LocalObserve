#!/usr/bin/env bash
# Shared runtime/Compose adapter for the local acceptance scripts.
#
# Source this file from a script that sets RUNTIME and, optionally,
# COMPOSE_PROJECT_NAME. It intentionally does not start an engine or install a
# Compose provider; those are host responsibilities documented in mise.toml.

runtime_binary() {
  local runtime="${1:-}"
  case "$runtime" in
    docker)
      command -v docker
      ;;
    podman)
      # mise's Linux package may expose only podman-remote.
      if command -v podman >/dev/null 2>&1; then
        command -v podman
      elif command -v podman-remote >/dev/null 2>&1; then
        command -v podman-remote
      else
        return 1
      fi
      ;;
    nerdctl)
      command -v nerdctl
      ;;
    *)
      echo "unknown runtime: $runtime" >&2
      return 1
      ;;
  esac
}

runtime_compose() {
  local runtime="${1:-}"
  shift || true

  local binary
  binary="$(runtime_binary "$runtime")" || return 127

  local project_args=()
  if [[ -n "${COMPOSE_PROJECT_NAME:-}" ]]; then
    project_args=(-p "$COMPOSE_PROJECT_NAME")
  fi

  "$binary" compose "${project_args[@]}" "$@"
}

runtime_engine_available() {
  local runtime="${1:-}"
  local binary
  binary="$(runtime_binary "$runtime")" || return 1
  "$binary" info >/dev/null 2>&1
}
