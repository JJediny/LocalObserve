#!/usr/bin/env bash
# check-ports.sh — Pre-flight check for published host port conflicts
#
# Warns or fails if any required LocalObserve published ports are bound by
# an external process or a duplicate Docker daemon (Issue #96).
set -euo pipefail

REQUIRED_TCP_PORTS=(5080 5081 4317 4318 9000 9090)
REQUIRED_UDP_PORTS=(2055 6343)

conflicts=()

host_port_in_use() {
  local protocol="$1"
  local port="$2"
  command -v ss >/dev/null 2>&1 || return 1
  ss -H -l"$protocol" 2>/dev/null \
    | awk '{print $4}' \
    | grep -qE "(:|\.)${port}$"
}

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

if [ ${#conflicts[@]} -gt 0 ]; then
  # Check if they belong to the current running localobserve stack
  if docker compose ps -q 2>/dev/null | grep -q .; then
    echo "[info] Ports in use by existing LocalObserve compose stack: ${conflicts[*]}"
    exit 0
  else
    echo "[!] Port conflict detected: required host ports are bound by another process/daemon:" >&2
    echo "    ${conflicts[*]}" >&2
    echo "    Ensure only one Docker daemon/context (default) is running the stack." >&2
    exit 1
  fi
fi

echo "[+] All required LocalObserve ports are available."
exit 0
