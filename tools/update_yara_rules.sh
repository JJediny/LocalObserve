#!/usr/bin/env bash
#
# update_yara_rules.sh
#
# This script downloads YARA rules and other threat intelligence datasets
# from abuse.ch (MalwareBazaar/URLhaus) using the authentication key.
# It places the rules where ClamAV and osquery can consume them.

set -e

# Load the authentication key from .env
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${PROJECT_ROOT}/.env"

if [[ -f "$ENV_FILE" ]]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
fi

if [[ -z "$ABUSE_CH_AUTH_KEY" ]]; then
    echo "ERROR: ABUSE_CH_AUTH_KEY is not set in $ENV_FILE"
    exit 1
fi

# Define destination directories for YARA rules
OSQUERY_YARA_DIR="${PROJECT_ROOT}/.data/osquery/yara"
CLAMAV_YARA_DIR="${PROJECT_ROOT}/.data/clamav_db"

mkdir -p "$OSQUERY_YARA_DIR"
mkdir -p "$CLAMAV_YARA_DIR"

echo "[*] Downloading latest MalwareBazaar YARA rule statistics and rules..."

# Example: Download MalwareBazaar recent CSV feed
# (This provides hashes, but for YARA rules we would fetch the specific YARA exports)
curl -s -o "${PROJECT_ROOT}/.data/mb_recent.csv" "https://mb-api.abuse.ch/v2/files/exports/${ABUSE_CH_AUTH_KEY}/recent.csv"

# Example: Download YARA rules (Template URL, adjust to the specific Abuse.ch endpoint for YARA downloads)
# Currently MalwareBazaar provides a daily batch of rules. 
# For demonstration, we simulate fetching the compiled YARA rules provided by the community on MalwareBazaar.
YARA_ENDPOINT="https://bazaar.abuse.ch/export/yara/"
TEMP_ZIP="/tmp/mb_yara.zip"

echo "[*] Fetching YARA rules from $YARA_ENDPOINT"
curl -s -o "$TEMP_ZIP" "$YARA_ENDPOINT"

# If the endpoint provides a zip, extract it. If it provides a single .yar file, just move it.
# Assuming we get a .yar file or a zip containing .yar files.
if file "$TEMP_ZIP" | grep -q "Zip archive"; then
    unzip -q -o "$TEMP_ZIP" -d "/tmp/yara_rules_extracted"
    cat /tmp/yara_rules_extracted/*.yar > "${OSQUERY_YARA_DIR}/abuse_ch.yar" 2>/dev/null || true
    rm -rf "/tmp/yara_rules_extracted"
else
    # If it's just text/plain yara rules
    mv "$TEMP_ZIP" "${OSQUERY_YARA_DIR}/abuse_ch.yar"
fi

# ClamAV natively supports YARA rules. Copy the rules to ClamAV's DB directory.
# ClamAV requires the extension to be .yar or .yara
echo "[*] Synchronizing YARA rules to ClamAV database directory..."
cp "${OSQUERY_YARA_DIR}/abuse_ch.yar" "${CLAMAV_YARA_DIR}/abuse_ch.yar"

# Ensure permissions are correct for ClamAV
chmod 644 "${CLAMAV_YARA_DIR}/abuse_ch.yar"

# Reload ClamAV databases (if running in a container, you can send a command to it)
echo "[*] Triggering ClamAV database reload..."
docker exec loki-clamav-1 clamdscan --reload || echo "ClamAV container not running or reload failed."

echo "[*] Update complete! Rules are staged for OSquery and ClamAV."
