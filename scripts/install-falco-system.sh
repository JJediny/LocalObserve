#!/usr/bin/env bash
# install-falco-system.sh — System-wide installation script for Falco 0.43.1
set -euo pipefail

TARBALL="/tmp/falco-install/falco-0.43.1-x86_64.tar.gz"
EXPECTED_SHA="c9dd114b19028f473f04860d89f841e879fa21d53e2b312123f5885934b58095"

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
sudo cat << 'EOF' | sudo tee /etc/falco/config.d/localobserve-output.yaml > /dev/null
json_output: true
file_output:
  enabled: true
  filename: /var/log/falco/events.jsonl
EOF

echo "[+] Falco 0.43.1 installed system-wide successfully!"
/usr/bin/falco --version || true
