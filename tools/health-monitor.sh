#!/bin/bash
# health-monitor.sh - Infrastructure health monitoring for the security stack
# Checks service health, disk space, and implements a dead man's switch
#
# Usage: Run via cron every 5 minutes: */5 * * * * /path/to/health-monitor.sh

set -euo pipefail

# Configuration
DATA_DIR="${DATA_DIR:-/home/john/loki/.data}"
HEARTBEAT_FILE="${DATA_DIR}/health/heartbeat"
HEARTBEAT_MAX_AGE_SECONDS=600
DISK_WARN_PERCENT=85
DISK_CRIT_PERCENT=95
LOG_FILE="${DATA_DIR}/health/health-monitor.log"

SERVICES=("falco" "openobserve" "otel-collector" "clamav" "clamav-scanner")

mkdir -p "$(dirname "$HEARTBEAT_FILE")"
mkdir -p "$(dirname "$LOG_FILE")"

log() {
  echo "[$(date -Iseconds)] $*" | tee -a "$LOG_FILE"
}

check_service_health() {
  local service="$1"
  if docker compose ps --services --filter "status=running" 2>/dev/null | grep -q "^${service}$"; then
    return 0
  else
    return 1
  fi
}

check_disk_space() {
  local usage
  usage=$(df "$DATA_DIR" | awk 'NR==2 {gsub(/%/,""); print $5}')
  if [ "$usage" -ge "$DISK_CRIT_PERCENT" ]; then
    log "CRITICAL: Disk usage at ${usage}% (threshold: ${DISK_CRIT_PERCENT}%)"
    send_alert "Disk-Critical" "Disk usage at ${usage}% on $(df "$DATA_DIR" | awk 'NR==2 {print $1}')" "critical"
    return 1
  elif [ "$usage" -ge "$DISK_WARN_PERCENT" ]; then
    log "WARNING: Disk usage at ${usage}% (threshold: ${DISK_WARN_PERCENT}%)"
    send_alert "Disk-Warning" "Disk usage at ${usage}% on $(df "$DATA_DIR" | awk 'NR==2 {print $1}')" "warning"
    return 0
  fi
  return 0
}

check_heartbeat() {
  if [ -f "$HEARTBEAT_FILE" ]; then
    local last_heartbeat
    last_heartbeat=$(stat -c %Y "$HEARTBEAT_FILE" 2>/dev/null || echo 0)
    local now
    now=$(date +%s)
    local age=$((now - last_heartbeat))
    if [ "$age" -gt "$HEARTBEAT_MAX_AGE_SECONDS" ]; then
      log "CRITICAL: Dead man's switch triggered - no heartbeat for ${age}s (max: ${HEARTBEAT_MAX_AGE_SECONDS}s)"
      send_alert "Dead-Mans-Switch" "No security events received for $((age / 60)) minutes" "critical"
      return 1
    fi
  else
    log "WARNING: No heartbeat file found at ${HEARTBEAT_FILE}"
  fi
  return 0
}

send_alert() {
  local alert_name="$1"
  local description="$2"
  local severity="$3"

  log "ALERT: ${alert_name} [${severity}] - ${description}"

  if command -v notify-send &>/dev/null && [ -n "${DISPLAY:-}" ]; then
    notify-send --urgency=critical --expire-time=30000 \
      "Health Alert: ${alert_name}" "${description}" 2>/dev/null || true
  fi

  if [ -n "${SLACK_WEBHOOK_URL:-}" ]; then
    curl -s -X POST "$SLACK_WEBHOOK_URL" \
      -H 'Content-type: application/json' \
      --data "{\"text\":\":rotating_light: *${alert_name}* [${severity}]: ${description}\"}" \
      >/dev/null 2>&1 || true
  fi

  if [ -n "${EMAIL_TO:-}" ] && command -v mail &>/dev/null; then
    echo "${description}" | mail -s "[Security] ${alert_name} [${severity}]" "$EMAIL_TO" 2>/dev/null || true
  fi
}

main() {
  log "=== Health check started ==="

  local failed_services=()
  for service in "${SERVICES[@]}"; do
    if ! check_service_health "$service"; then
      failed_services+=("$service")
      log "DOWN: ${service}"
      send_alert "Service-Down" "Security service ${service} is not running" "critical"
    fi
  done

  if [ ${#failed_services[@]} -eq 0 ]; then
    log "OK: All services running"
  fi

  check_disk_space || true
  check_heartbeat || true

  log "=== Health check completed ==="
}

main "$@"
