#!/usr/bin/env bash
# install-falco-system.sh — System-wide installation script for Falco 0.43.1
#
# Modes:
#   (no args)           — full tarball install (binary + configs + drop-in)
#   --config-only       — only (re)wire Falco output for LocalObserve on an
#                         EXISTING distro/package install; never touches the
#                         binary, so a newer distro Falco is not downgraded.
#                         Usage: sudo bash scripts/install-falco-system.sh --config-only
set -euo pipefail

TARBALL="/tmp/falco-install/falco-0.43.1-x86_64.tar.gz"
EXPECTED_SHA="c9dd114b19028f473f04860d89f841e879fa21d53e2b312123f5885934b58095"

FALCO_OUTPUT_DIR="/var/log/falco"
FALCO_CONFIG_DROPIN="/etc/falco/config.d/localobserve-output.yaml"
FALCO_SERVICES=(falco-modern-bpf falco)

write_localobserve_output_config() {
    # Distro falco.yaml defaults (json_output: false, priority: debug,
    # file_output disabled) combined with systemd StandardOutput=null mean
    # detections are silently DISCARDED. Override them: JSON file output for
    # the LocalObserve otel-collector, and priority: warning to match the
    # container profile (falco-config.yaml) so events.jsonl write volume stays
    # bounded — a debug-priority firehose would waste SSD I/O.
    sudo mkdir -p "$FALCO_OUTPUT_DIR"
    sudo tee "$FALCO_CONFIG_DROPIN" > /dev/null << 'EOF'
# LocalObserve: JSON file output consumed by the otel-collector
# (file_log/falco receiver, /var/log/falco bind mount).
json_output: true
priority: warning
file_output:
  enabled: true
  filename: /var/log/falco/events.jsonl
EOF
}

restart_falco() {
    local svc
    for svc in "${FALCO_SERVICES[@]}"; do
        if systemctl list-unit-files 2>/dev/null | grep -q "^${svc}\.service"; then
            sudo systemctl restart "$svc"
            echo "[+] Restarted ${svc}; host Falco now writes JSON to ${FALCO_OUTPUT_DIR}/events.jsonl"
            return 0
        fi
    done
    echo "[!] No systemd falco unit found; restart Falco manually to apply ${FALCO_CONFIG_DROPIN}" >&2
}

if [ "${1:-}" = "--config-only" ]; then
    if [ "$(id -u)" -ne 0 ]; then
        echo "run as root: sudo bash $0 --config-only" >&2
        exit 1
    fi
    if [ ! -x /usr/bin/falco ] && ! command -v falco >/dev/null 2>&1; then
        echo "[!] No existing Falco install found; run the full install mode instead." >&2
        exit 1
    fi
    write_localobserve_output_config
    restart_falco
    echo "[+] Done. Verify with: journalctl -u falco-modern-bpf -n 5 or ls -la /var/log/falco/"
    exit 0
fi

if [ ! -f "$TARBALL" ]; then
    echo "[*] Downloading Falco 0.43.1..."
    mkdir -p /tmp/falco-install
    curl -SL -o "$TARBALL" https://download.falco.org/packages/bin/x86_64/falco-0.43.1-x86_64.tar.gz
fi

echo "[*] Verifying SHA256 integrity..."
echo "$EXPECTED_SHA  $TARBALL" | sha256sum --check -

echo "[*] Extracting..."
tar -xzf "$TARBALL" -C /tmp/falco-install

echo "[*] Installing binary and configurations to system paths (requires sudo)..."
sudo cp /tmp/falco-install/falco-0.43.1-x86_64/usr/bin/falco /usr/bin/falco
sudo chmod 755 /usr/bin/falco

sudo mkdir -p /etc/falco /var/log/falco
sudo cp -r /tmp/falco-install/falco-0.43.1-x86_64/etc/falco/* /etc/falco/

# Enable modern_ebpf engine
sudo sed -i 's/kind: .*/kind: modern_ebpf/' /etc/falco/falco.yaml 2>/dev/null || true

# Enable JSON file output for LocalObserve ingestion
write_localobserve_output_config

echo "[+] Falco 0.43.1 installed system-wide successfully!"
/usr/bin/falco --version || true
