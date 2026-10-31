#!/usr/bin/env bash
# Manage the LocalObserve watcher for native Zed agent sessions.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${LOCALOBSERVE_AGENT_STATE_DIR:-$ROOT/.data/agent-sessions}"
PID_FILE="$STATE_DIR/zed-observer.pid"
LOG_FILE="$STATE_DIR/zed-observer.log"

mkdir -p "$STATE_DIR"

running_pid() {
    [[ -f "$PID_FILE" ]] || return 1
    local pid
    pid="$(cat "$PID_FILE")"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    ps -p "$pid" -o args= | grep -q '[z]ed_agent_observer.py' || return 1
    printf '%s\n' "$pid"
}

start() {
    local pid
    if pid="$(running_pid)"; then
        echo "Zed agent observer already running (PID $pid)"
        return 0
    fi
    rm -f "$PID_FILE"
    cd "$ROOT"
    nohup mise exec uv -- uv run python tools/zed_agent_observer.py \
        >>"$LOG_FILE" 2>&1 </dev/null &
    pid=$!
    echo "$pid" >"$PID_FILE"
    sleep 1
    if ! kill -0 "$pid" 2>/dev/null; then
        rm -f "$PID_FILE"
        echo "Zed agent observer failed to start; see $LOG_FILE" >&2
        return 1
    fi
    echo "Zed agent observer started (PID $pid); log: $LOG_FILE"
}

stop() {
    local pid
    if ! pid="$(running_pid)"; then
        rm -f "$PID_FILE"
        echo "Zed agent observer is not running"
        return 0
    fi
    kill "$pid"
    for _ in {1..20}; do
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$PID_FILE"
            echo "Zed agent observer stopped"
            return 0
        fi
        sleep 0.25
    done
    echo "Zed agent observer did not stop within 5 seconds (PID $pid)" >&2
    return 1
}

status() {
    local pid
    if pid="$(running_pid)"; then
        echo "Zed agent observer is running (PID $pid)"
        echo "Log: $LOG_FILE"
    else
        rm -f "$PID_FILE"
        echo "Zed agent observer is not running"
        return 1
    fi
}

case "${1:-status}" in
    start) start ;;
    stop) stop ;;
    restart) stop; start ;;
    status) status ;;
    *) echo "Usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
