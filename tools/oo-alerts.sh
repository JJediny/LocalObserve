#!/usr/bin/env bash
# oo-alerts.sh - Sync OpenObserve alert destinations and alert rules
# Usage: ./tools/oo-alerts.sh {setup-destination|import|export|test}
set -e

OO_URL="${OO_URL:-http://localhost:5080}"
OO_ORG="${OO_ORG:-default}"
OO_USER="${OO_USER:-root@example.com}"
OO_PASS="${OO_PASS:-Complexpass#123}"
ALERTS_FILE="${ALERTS_FILE:-./alerts/openobserve/alerts.json}"
WEBHOOK_URL="${WEBHOOK_URL:-http://alert-receiver:9000/hooks/security-alert-open}"

function setup_destination() {
  echo "[*] Registering localhost webhook as OpenObserve alert destination..."
  DEST_PAYLOAD=$(cat <<EOF
{
  "name": "localhost-webhook",
  "template": "prebuilt_webhook",
  "url": "${WEBHOOK_URL}",
  "method": "post",
  "skip_tls_verify": false,
  "headers": {}
}
EOF
)
  RESULT=$(curl -s -o /tmp/oo_dest_resp.json -w "%{http_code}" \
    -u "${OO_USER}:${OO_PASS}" \
    -X POST "${OO_URL}/api/${OO_ORG}/alerts/destinations" \
    -H "Content-Type: application/json" \
    -d "${DEST_PAYLOAD}")
  echo "[*] Destination registration status: HTTP ${RESULT}: $(cat /tmp/oo_dest_resp.json 2>/dev/null)"
}

function import_alerts() {
  echo "[*] Importing alerts from ${ALERTS_FILE}..."
  [ -f "$ALERTS_FILE" ] || { echo "ERROR: ${ALERTS_FILE} not found"; exit 1; }

  ALERTS=$(cat "$ALERTS_FILE")
  COUNT=$(echo "$ALERTS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
  echo "[*] Found ${COUNT} alert definitions"

  echo "$ALERTS" | python3 -c "
import sys, json
alerts = json.load(sys.stdin)
for a in alerts:
    print(json.dumps(a))
" | while IFS= read -r alert; do
    NAME=$(echo "$alert" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])")
    HTTP=$(curl -s -o /tmp/oo_alert_resp.json -w "%{http_code}" \
      -u "${OO_USER}:${OO_PASS}" \
      -X POST "${OO_URL}/api/v2/${OO_ORG}/alerts" \
      -H "Content-Type: application/json" \
      -d "$alert")
    echo "  [${HTTP}] ${NAME}: $(cat /tmp/oo_alert_resp.json 2>/dev/null)"
  done
  echo "[*] Import complete."
}

function export_alerts() {
  echo "[*] Exporting alerts from OpenObserve..."
  RESULT=$(curl -s -u "${OO_USER}:${OO_PASS}" "${OO_URL}/api/v2/${OO_ORG}/alerts")
  echo "$RESULT" | python3 -c "
import sys,json
data = json.load(sys.stdin)
alerts = data.get('list', data) if isinstance(data, dict) else data
print(json.dumps(alerts, indent=2))
" > "$ALERTS_FILE"
  COUNT=$(python3 -c "import json; d=json.load(open('${ALERTS_FILE}')); print(len(d) if isinstance(d,list) else 0)" 2>/dev/null || echo "?")
  echo "[*] Exported ${COUNT} alerts to ${ALERTS_FILE}"
}

function test_webhook() {
  echo "[*] Testing webhook at ${WEBHOOK_URL}..."
  curl -s -X POST "http://localhost:9000/hooks/security-alert-open" \
    -H "Content-Type: application/json" \
    -d '{"alert_name":"Test Alert","severity":"info","description":"LocalObserve webhook connectivity test"}' && echo ""
  echo "[*] Test payload sent. Check your desktop for a notification."
}

case "$1" in
  setup-destination) setup_destination ;;
  import)            import_alerts ;;
  export)            export_alerts ;;
  test)              test_webhook ;;
  *)
    echo "Usage: $0 {setup-destination|import|export|test}"
    exit 1
    ;;
esac
