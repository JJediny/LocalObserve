#!/bin/bash
# alert-watcher.sh - Host-side service that watches for alert files from the webhook container
# and triggers desktop notifications via notify-send.
#
# This bridges the container-to-host dbus gap by using a shared directory.
#
# Usage: Run as a systemd service or background process
#   systemctl enable --now alert-watcher.service
#   OR: nohup ./alert-watcher.sh &

set -uo pipefail

ALERT_DIR="${ALERT_DIR:-/home/john/loki/.data/alerts}"
PROCESSED_DIR="${ALERT_DIR}/processed"
POLL_INTERVAL="${POLL_INTERVAL:-2}"

mkdir -p "$ALERT_DIR" "$PROCESSED_DIR"

log() {
  echo "[$(date -Iseconds)] $*"
}

process_alert() {
  local file="$1"
  local basename
  basename=$(basename "$file")

  # Parse JSON fields (using grep/sed to avoid jq dependency)
  local title severity body
  title=$(grep -o '"title": *"[^"]*"' "$file" | head -1 | cut -d'"' -f4)
  severity=$(grep -o '"severity": *"[^"]*"' "$file" | head -1 | cut -d'"' -f4)
  body=$(grep -o '"body": *"[^"]*"' "$file" | head -1 | cut -d'"' -f4)

  if [ -z "$title" ]; then
    log "WARNING: Could not parse alert file: $file"
    mv "$file" "$PROCESSED_DIR/"
    return
  fi

  local icon="dialog-warning"
  if echo "$severity" | grep -qi "critical\|high\|error"; then
    icon="dialog-error"
  fi

  log "Sending desktop notification: $title"

  notify-send \
    --urgency=critical \
    --expire-time=30000 \
    --icon="$icon" \
    "$title" \
    "$body" 2>/dev/null || log "Failed to send notification for: $title"

  # Move to processed after a delay (allow viewer to see it)
  sleep 5
  mv "$file" "$PROCESSED_DIR/"

  # Clean up old processed alerts (older than 24 hours)
  find "$PROCESSED_DIR" -name "*.json" -mtime +1 -delete 2>/dev/null || true
}

log "Alert watcher started. Watching: $ALERT_DIR"

while true; do
  for file in "$ALERT_DIR"/*.json; do
    [ -f "$file" ] || continue
    process_alert "$file"
  done
  sleep "$POLL_INTERVAL"
done
