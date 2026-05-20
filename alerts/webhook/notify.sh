#!/bin/sh
# notify.sh - Runs inside the webhook container
# Routes OpenObserve alerts to multiple notification channels:
#   1. File-based bridge for host notify-send (reliable across container boundaries)
#   2. Slack webhook (if SLACK_WEBHOOK_URL is set)
#   3. Email (if EMAIL_TO is set and mail is available)
#   4. Generic webhook (for PagerDuty, Discord, etc.)
#   5. Stdout log (always)
#
# Environment variables set by webhook:
#   $1           = alert_name  (from payload.alert_name if mapped)
#   $2           = severity    (from payload.severity)
#   $3           = description (from payload.description)
#   $PAYLOAD     = full raw JSON payload

ALERT_DIR="/var/log/alerts"
mkdir -p "$ALERT_DIR"

# Extract fields from the PAYLOAD in a tolerant way. Falco's http_output
# emits JSON with keys like 'rule', 'priority', and 'output' rather than
# alert_name/severity/description. Try several common paths and fall back
# to sensible defaults.
ALERT_NAME="${1:-$(echo "$PAYLOAD" | sed -n 's/.*"alert_name"\s*:\s*"\([^"]*\)".*/\1/p; s/.*"rule"\s*:\s*"\([^"]*\)".*/\1/p' | head -1)}"
SEVERITY="${2:-$(echo "$PAYLOAD" | sed -n 's/.*"severity"\s*:\s*"\([^"]*\)".*/\1/p; s/.*"priority"\s*:\s*"\([^"]*\)".*/\1/p; s/.*"priority"\s*:\s*\([^,}]*\).*/\1/p' | head -1)}"
DESCRIPTION="${3:-$(echo "$PAYLOAD" | sed -n 's/.*"description"\s*:\s*"\([^"]*\)".*/\1/p; s/.*"output"\s*:\s*"\([^"]*\)".*/\1/p' | head -1)}"

# If no alert name found, try to build one from rule or other fields
if [ -z "$ALERT_NAME" ]; then
  ALERT_NAME="$(echo "$PAYLOAD" | sed -n 's/.*"rule"\s*:\s*"\([^"]*\)".*/\1/p' | head -1)"
fi
# severity fallback
if [ -z "$SEVERITY" ]; then
  SEVERITY="$(echo "$PAYLOAD" | sed -n 's/.*"priority"\s*:\s*"\([^"]*\)".*/\1/p; s/.*"priority"\s*:\s*\([^,}]*\).*/\1/p' | head -1)"
fi
# description fallback
if [ -z "$DESCRIPTION" ]; then
  DESCRIPTION="$(echo "$PAYLOAD" | sed -n 's/.*"output"\s*:\s*"\([^"]*\)".*/\1/p' | head -1)"
fi

TITLE="LocalObserve Alert: ${ALERT_NAME:-Security Event}"
BODY="${DESCRIPTION:-No description provided} [Severity: ${SEVERITY:-unknown}]"
TIMESTAMP="$(date -Iseconds)"
ALERT_ID="$(date +%s%N | cut -c1-13)"

# --- Output 1: Log to stdout (captured by Docker) ---
echo "[${TIMESTAMP}] ALERT | ${TITLE} | ${BODY}"

# --- Output 2: File-based bridge for host notifications ---
# Write alert to a file that the host-side watcher reads and triggers notify-send
cat > "${ALERT_DIR}/${ALERT_ID}.json" <<EOF
{
  "timestamp": "${TIMESTAMP}",
  "alert_name": "${ALERT_NAME}",
  "severity": "${SEVERITY}",
  "description": "${DESCRIPTION}",
  "title": "${TITLE}",
  "body": "${BODY}"
}
EOF

# Also try direct notify-send (works if dbus is properly bridged)
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/1000/bus}"
export DISPLAY="${DISPLAY:-:0}"

ICON="dialog-warning"
if echo "$SEVERITY" | grep -qi "critical\|high\|error"; then
  ICON="dialog-error"
fi

notify-send \
  --urgency=critical \
  --expire-time=30000 \
  --icon="${ICON}" \
  "${TITLE}" \
  "${BODY}" 2>/dev/null || true

# --- Output 3: Slack webhook ---
if [ -n "$SLACK_WEBHOOK_URL" ]; then
  SLACK_COLOR="#ff0000"
  if echo "$SEVERITY" | grep -qi "warning"; then
    SLACK_COLOR="#ffaa00"
  elif echo "$SEVERITY" | grep -qi "info\|low"; then
    SLACK_COLOR="#00aa00"
  fi

  curl -s -X POST "$SLACK_WEBHOOK_URL" \
    -H 'Content-type: application/json' \
    --data "{
      \"attachments\": [{
        \"color\": \"${SLACK_COLOR}\",
        \"title\": \"${TITLE}\",
        \"text\": \"${BODY}\",
        \"ts\": $(date +%s)
      }]
    }" >/dev/null 2>&1 || echo "[${TIMESTAMP}] Slack notification failed"
fi

# --- Output 4: Email ---
if [ -n "$EMAIL_TO" ] && command -v mail >/dev/null 2>&1; then
  echo "${BODY}" | mail -s "[Security Alert] ${ALERT_NAME}" "$EMAIL_TO" 2>/dev/null || \
    echo "[${TIMESTAMP}] Email notification failed"
fi

# --- Output 5: Generic webhook (for PagerDuty, Discord, etc.) ---
if [ -n "$GENERIC_WEBHOOK_URL" ]; then
  curl -s -X POST "$GENERIC_WEBHOOK_URL" \
    -H 'Content-type: application/json' \
    --data "{
      \"alert_name\": \"${ALERT_NAME}\",
      \"severity\": \"${SEVERITY}\",
      \"description\": \"${DESCRIPTION}\",
      \"timestamp\": \"${TIMESTAMP}\"
    }" >/dev/null 2>&1 || echo "[${TIMESTAMP}] Generic webhook notification failed"
fi
