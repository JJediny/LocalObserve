#!/usr/bin/env bash
# install-logrotate.sh — Host logrotate installation and verification for LocalObserve
#
# Usage:
#   sudo bash scripts/install-logrotate.sh           # Install /etc/logrotate.d/localobserve
#   bash scripts/install-logrotate.sh --dry-run     # Validate syntax and test run without modifying files
#   bash scripts/install-logrotate.sh --status      # Check log sizes and rotation status
#   sudo bash scripts/install-logrotate.sh --force  # Force rotation immediately
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_CONF="${REPO_ROOT}/scripts/logrotate-localobserve.conf"
TARGET_CONF="/etc/logrotate.d/localobserve"

generate_config() {
    local target_file="$1"
    # Replace default path with actual repo root if different
    sed "s|/home/john/LocalObserve|${REPO_ROOT}|g" "$SOURCE_CONF" > "$target_file"
}

case "${1:-}" in
    --dry-run)
        tmp_conf=$(mktemp)
        generate_config "$tmp_conf"
        echo "[*] Testing logrotate configuration syntax (dry-run)..."
        logrotate -d "$tmp_conf"
        rm -f "$tmp_conf"
        echo "[+] Logrotate configuration is valid."
        exit 0
        ;;
    --status)
        echo "=== LocalObserve Log File Status ==="
        for f in "${REPO_ROOT}"/.data/{osquery/osqueryd.results.log,falco/events.jsonl,clamav/scan.log,goflow2/flows.jsonl}; do
            if [ -f "$f" ]; then
                ls -lh "$f"
            else
                echo "  (not present): $f"
            fi
        done
        if [ -f "$TARGET_CONF" ]; then
            echo "[+] Installed at: $TARGET_CONF"
        else
            echo "[!] Not installed at: $TARGET_CONF"
        fi
        exit 0
        ;;
    --force)
        tmp_conf=$(mktemp)
        generate_config "$tmp_conf"
        mkdir -p "${REPO_ROOT}/.data"
        echo "[*] Forcing rotation of LocalObserve logs..."
        logrotate -s "${REPO_ROOT}/.data/logrotate.status" -f "$tmp_conf"
        rm -f "$tmp_conf"
        echo "[+] Successfully forced rotation of LocalObserve logs."
        exit 0
        ;;
    --install|"")
        if [ "$(id -u)" -ne 0 ]; then
            echo "Error: installation requires root privileges." >&2
            echo "Usage: sudo bash $0" >&2
            exit 1
        fi
        tmp_conf=$(mktemp)
        generate_config "$tmp_conf"
        install -m 0644 "$tmp_conf" "$TARGET_CONF"
        rm -f "$tmp_conf"
        echo "[+] Successfully installed $TARGET_CONF"
        echo "[+] LocalObserve log files will now be rotated weekly or when exceeding maxsize (50M/100M)."
        exit 0
        ;;
    *)
        echo "Usage: $0 [--install|--dry-run|--status|--force]" >&2
        exit 1
        ;;
esac
