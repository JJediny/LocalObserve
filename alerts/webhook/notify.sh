#!/bin/sh
# notify.sh - Runs inside the webhook container
# Routes OpenObserve alerts to the host's notify-send or terminal/log
#
# Environment variables set by webhook:
#   $1           = alert_name  (from payload.alert_name if mapped)
#   $2           = severity    (from payload.severity)
#   $3           = description (from payload.description)
#   $PAYLOAD     = full raw JSON payload

ALERT_NAME="${1:-$(echo "$PAYLOAD" | grep -o '"alert_name":"[^"]*"' | cut -d'"' -f4)}"
SEVERITY="${2:-$(echo "$PAYLOAD" | grep -o '"severity":"[^"]*"' | cut -d'"' -f4)}"
DESCRIPTION="${3:-$(echo "$PAYLOAD" | grep -o '"description":"[^"]*"' | cut -d'"' -f4)}"

# Fallback for OpenObserve native webhook schema
if [ -z "$ALERT_NAME" ]; then
  ALERT_NAME="$(echo "$PAYLOAD" | grep -o '"alert_name":"[^"]*"' | head -1 | cut -d'"' -f4)"
fi
if [ -z "$SEVERITY" ]; then
  SEVERITY="$(echo "$PAYLOAD" | grep -o '"alert_type":"[^"]*"' | head -1 | cut -d'"' -f4)"
fi

TITLE="🚨 LocalObserve Alert: ${ALERT_NAME:-Security Event}"
BODY="${DESCRIPTION:-No description provided} [Severity: ${SEVERITY:-unknown}]"
TIMESTAMP="$(date -Iseconds)"

# --- Output 1: Log to stdout (captured by Docker / OTEL) ---
echo "[${TIMESTAMP}] ALERT | ${TITLE} | ${BODY}"
echo "[${TIMESTAMP}] PAYLOAD | ${PAYLOAD}"

# --- Output 2: notify-send on host display (via host DBUS/X11) ---
# The container must have DISPLAY and DBUS_SESSION_BUS_ADDRESS set,
# and /run/user/1000 mounted as a volume (see docker-compose).
ICON="dialog-warning"
if echo "$SEVERITY" | grep -qi "critical\|high\|error"; then
  ICON="dialog-error"
fi

notify-send \
  --urgency=critical \
  --expire-time=30000 \
  --icon="${ICON}" \
  "${TITLE}" \
  "${BODY}" 2>/dev/null || \
  echo "[${TIMESTAMP}] notify-send unavailable, alert logged only"
