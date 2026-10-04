# Falco Host Installation & LocalObserve Pipeline Integration

This guide documents the procedures for installing Falco 0.45.0 on Linux host systems, verifying package integrity, configuring kernel telemetry outputs, and integrating with the LocalObserve observability pipeline.

---

## 1. Overview & Distribution Discovery

Falco is a kernel runtime security tool that uses eBPF (modern_ebpf) or a kernel module to monitor system call events. In LocalObserve, Falco acts as a host kernel telemetry generator alongside osquery.

LocalObserve supports two deployment models:
1. **Host-Native Falco** (*Recommended for Linux endpoints*): Falco runs as a systemd service (`falco-modern-bpf.service`), writing events to `/var/log/falco/events.jsonl`, which is bind-mounted into the OpenTelemetry Collector container.
2. **Containerized Falco**: Pinned to `falcosecurity/falco:0.45.0`, opt-in via `--profile agents`.

> [!IMPORTANT]
> **Package Sources**: Official Falco Linux binary tarballs are distributed via `https://download.falco.org/packages/bin/`. Official Debian/Ubuntu APT packages are hosted at `https://download.falco.org/packages/deb`.

### Release Details
- **Version**: `0.45.0`
- **Architecture**: `x86_64`
- **Tarball URL**: `https://download.falco.org/packages/bin/x86_64/falco-0.45.0-x86_64.tar.gz`
- **Expected SHA256**: `6c8c591089db4ccf815c1761be28109b46f2c14d462a8414abcdd282249aeefe`

---

## 2. Installation Methods

### Method A: Official APT Repository (Recommended on Ubuntu / Debian)

On modern Ubuntu (22.04 LTS / 24.04 LTS):

```bash
# 1. Trust Falco signing key
curl -fsSL https://falco.org/repo/falcosecurity-packages.asc | \
  sudo gpg --dearmor -o /usr/share/keyrings/falco-archive-keyring.gpg

# 2. Configure Falco APT repository
echo "deb [signed-by=/usr/share/keyrings/falco-archive-keyring.gpg] https://download.falco.org/packages/deb stable main" | \
  sudo tee /etc/apt/sources.list.d/falcosecurity.list

# 3. Update and install falco
sudo apt update
sudo apt install -y falco
```

After installing via APT, run the LocalObserve output and permission wiring script:
```bash
sudo bash scripts/install-falco-system.sh --config-only
```

### Method B: Binary Tarball Installation

Before installing or running Falco from tarball, verify the SHA256 checksum:

```bash
# 1. Download official archive
mkdir -p /tmp/falco-install
cd /tmp/falco-install
curl -SLO https://download.falco.org/packages/bin/x86_64/falco-0.45.0-x86_64.tar.gz

# 2. Verify SHA256 checksum
echo "6c8c591089db4ccf815c1761be28109b46f2c14d462a8414abcdd282249aeefe  falco-0.45.0-x86_64.tar.gz" | sha256sum --check -

# 3. Extract contents
tar -xzf falco-0.45.0-x86_64.tar.gz

# 4. Install binary and rules to system paths
sudo cp falco-0.45.0-x86_64/usr/bin/falco /usr/bin/falco
sudo chmod 755 /usr/bin/falco
sudo mkdir -p /etc/falco /var/log/falco
sudo cp -r falco-0.45.0-x86_64/etc/falco/* /etc/falco/

# 5. Wire output configuration and permissions
sudo bash scripts/install-falco-system.sh --config-only
```

---

## 3. Host Systemd & Permission Integration

### The UMask & Permission Requirement

By default, upstream Falco systemd units (`falco-modern-bpf.service` / `falco.service`) specify `UMask=0077`. This causes `/var/log/falco/events.jsonl` to be created with `0600` (root-only) permissions.

The OpenTelemetry Collector container runs unprivileged as UID `10001:10001`. If `/var/log/falco/events.jsonl` is `0600`, the collector logs `permission denied` and cannot ingest detections.

The `scripts/install-falco-system.sh` script automatically applies a systemd drop-in override:
`/etc/systemd/system/falco-modern-bpf.service.d/localobserve-umask.conf`:
```ini
[Service]
UMask=0022
```

This guarantees that `events.jsonl` is created with mode `0644` (world-readable), enabling seamless collector ingestion.

### LocalObserve Output Configuration

The script places `/etc/falco/config.d/localobserve-output.yaml`:
```yaml
json_output: true
priority: warning
file_output:
  enabled: true
  filename: /var/log/falco/events.jsonl
```

---

## 4. LocalObserve Pipeline Integration

Falco events flow through the LocalObserve security pipeline as follows:

```
┌──────────────────┐     JSON Lines     ┌──────────────────────┐     OTTL / OTLP    ┌──────────────────┐
│  Falco Daemon    │ ─────────────────> │ OTel Collector       │ ─────────────────> │ OpenObserve      │
│  (host/container)│ /var/log/falco/    │ (filelog receiver)   │                    │ Stream: falco    │
└──────────────────┘ events.jsonl       └──────────────────────┘                    └──────────────────┘
                                                   │
                                                   │ Rule Matching
                                                   ▼
                                        ┌──────────────────────┐     Webhook        ┌──────────────────┐
                                        │ rsigma Detection     │ ─────────────────> │ Alert Receiver   │
                                        │ (Streaming Daemon)   │                    │ /var/log/alerts  │
                                        └──────────────────────┘                    └──────────────────┘
```

1. **Log Location**: Falco writes structured JSON security events to `/var/log/falco/events.jsonl` on the host (bind-mounted into the collector container at `/var/log/falco-host`).
2. **OTel Collector Ingestion**: The OTel Collector `file_log/falco` receiver tails this file, parses JSON attributes, and assigns resource attributes (`log.source: falco-file`, `service.name: falco`).
3. **Pipeline Mapping**: `rules/sigma/pipelines/localobserve_pipeline.yaml` maps Falco's `output_fields.proc.cmdline` and process fields to Sigma standard schema names.
4. **rsigma Detection & Alerts**: rsigma ingests process/kernel events, evaluates active Sigma rules, and issues HTTP POST webhooks to the `alert-receiver` service upon detection.

---

## 5. Verification Checklist

- [x] Falco binary verified with version `0.45.0`.
- [x] Service running via modern eBPF: `systemctl status falco-modern-bpf.service`.
- [x] Systemd UMask drop-in applied: `/etc/systemd/system/falco-modern-bpf.service.d/localobserve-umask.conf`.
- [x] Log file permissions verified: `-rw-r--r-- 1 root root ... /var/log/falco/events.jsonl`.
- [x] Collector tailing confirmed: OpenTelemetry Collector logs `"Started watching file /var/log/falco-host/events.jsonl"`.
- [x] End-to-end detection verified: running `cat /etc/shadow` creates a `Read sensitive file untrusted` event appearing in OpenObserve's `falco` stream.
