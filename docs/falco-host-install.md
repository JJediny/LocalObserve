# Falco Host Installation & LocalObserve Pipeline Integration

This guide documents the procedures for installing Falco 0.43.1 on Linux host systems, verifying package integrity, configuring kernel telemetry outputs, and integrating with the LocalObserve observability pipeline.

---

## 1. Overview & Distribution Discovery

Falco is a kernel runtime security tool that uses eBPF or a kernel module to monitor system call events. In LocalObserve, Falco acts as a host kernel telemetry generator alongside osquery.

> [!IMPORTANT]
> **Binary Package Source**: Official Falco Linux binary tarballs are distributed via `https://download.falco.org/packages/bin/` rather than directly on GitHub release pages (where assets are restricted to debug symbols and source packages).

### Release Details
- **Version**: `0.43.1`
- **Architecture**: `x86_64`
- **Tarball URL**: `https://download.falco.org/packages/bin/x86_64/falco-0.43.1-x86_64.tar.gz`
- **Expected SHA256**: `c9dd114b19028f473f04860d89f841e879fa21d53e2b312123f5885934b58095`

---

## 2. Integrity Verification & Extraction

Before installing or running Falco, always verify the SHA256 checksum of the downloaded archive.

```bash
# 1. Download official archive
mkdir -p /tmp/falco-install
cd /tmp/falco-install
curl -SLO https://download.falco.org/packages/bin/x86_64/falco-0.43.1-x86_64.tar.gz

# 2. Verify SHA256 checksum
echo "c9dd114b19028f473f04860d89f841e879fa21d53e2b312123f5885934b58095  falco-0.43.1-x86_64.tar.gz" | sha256sum --check -

# 3. Extract contents
tar -xzf falco-0.43.1-x86_64.tar.gz
```

---

## 3. User-Local Installation (Development & Testing)

For non-root development or testing environments where `sudo` access is restricted, install Falco into user-local directory structures (`~/.local` and `~/.config`).

### Step-by-Step User-Local Setup

```bash
# Create local directory paths
mkdir -p ~/.local/bin ~/.config/falco

# Copy executable binary
cp falco-0.43.1-x86_64/usr/bin/falco ~/.local/bin/

# Copy default rules & configuration templates
cp -r falco-0.43.1-x86_64/etc/falco/* ~/.config/falco/

# Verify binary execution & version
~/.local/bin/falco --version
```

### Validating Rules & Configuration

To validate rules or test syntax using user-local configuration files:

```bash
~/.local/bin/falco -c falco-config.yaml -r ~/.config/falco/falco_rules.yaml --list rules
```

---

## 4. System-Wide Installation (Production Host Deployment)

For production Linux endpoints requiring continuous system call monitoring via systemd and eBPF:

```bash
# 1. Move binary to system path
sudo cp falco-0.43.1-x86_64/usr/bin/falco /usr/bin/falco
sudo chmod 755 /usr/bin/falco

# 2. Install system configuration & rules
sudo mkdir -p /etc/falco /var/log/falco
sudo cp -r falco-0.43.1-x86_64/etc/falco/* /etc/falco/

# 3. Configure modern_ebpf engine in /etc/falco/falco.yaml
sudo sed -i 's/kind: .*/kind: modern_ebpf/' /etc/falco/falco.yaml

# 4. Enable JSON file output for LocalObserve ingestion
sudo cat << 'EOF' | sudo tee /etc/falco/config.d/localobserve-output.yaml
json_output: true
file_output:
  enabled: true
  filename: /var/log/falco/events.jsonl
EOF

# 5. Verify system configuration
falco --list rules
```

### Systemd Service Configuration

Create `/etc/systemd/system/falco.service`:

```ini
[Unit]
Description=Falco Kernel Security Telemetry Collector
Documentation=https://falco.org/docs/
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/falco -c /etc/falco/falco.yaml
Restart=on-failure
RestartSec=5s
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now falco
```

---

## 5. LocalObserve Pipeline Integration

Falco events flow through the LocalObserve security pipeline as follows:

```
┌──────────────────┐     JSON Lines     ┌──────────────────────┐     OTTL / OTLP    ┌──────────────────┐
│  Falco Daemon    │ ─────────────────> │ OTel Collector       │ ─────────────────> │ OpenObserve      │
│  (host/container)│ .data/falco/       │ (filelog receiver)   │                    │ Stream: falco    │
└──────────────────┘ events.jsonl       └──────────────────────┘                    └──────────────────┘
                                                   │
                                                   │ Rule Matching
                                                   ▼
                                        ┌──────────────────────┐     Webhook        ┌──────────────────┐
                                        │ rsigma Detection     │ ─────────────────> │ Alert Receiver   │
                                        │ (Streaming Daemon)   │                    │ /var/log/alerts  │
                                        └──────────────────────┘                    └──────────────────┘
```

1. **Log Location**: Falco writes structured JSON security events to `./.data/falco/events.jsonl`.
2. **OTel Collector Ingestion**: The OTel Collector `filelog/falco` receiver tails this file, parses JSON attributes, and assigns `log_type: falco`.
3. **Pipeline Mapping**: `rules/sigma/pipelines/localobserve_pipeline.yaml` maps Falco's `output_fields.proc.cmdline` and process fields to Sigma standard schema names.
4. **rsigma Detection & Alerts**: rsigma ingests process/kernel events, evaluates active Sigma rules (such as `rules/sigma/active_rules/suspicious_unshare.yaml`), and issues HTTP POST webhooks to the `alert-receiver` service upon detection.

---

## 6. Verification Checklist

- [x] Falco binary verified with SHA256 (`c9dd114b19028f473f04860d89f841e879fa21d53e2b312123f5885934b58095`).
- [x] `--version` returns `0.43.1`.
- [x] Config schema validation succeeds with `falco -c falco-config.yaml`.
- [x] Integration tests pass with `uv run pytest --run-stack tests/test_rsigma_alerts.py`.
