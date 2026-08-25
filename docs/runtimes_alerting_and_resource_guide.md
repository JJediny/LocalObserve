# LocalObserve Multi-Runtime Deployment, Resource Profiling & Alerting Guide

This guide documents the cross-runtime support matrix for Docker, Podman, and Nerdctl Compose, details resource optimization strategies (RAM, CPU, and Filesystems), provides step-by-step alerting setup instructions, and links directly to diagnostic and debugging references.

---

## 1. Multi-Runtime Support Matrix (Docker, Podman, Nerdctl)

LocalObserve supports deployment across all major Linux container runtimes. Execution scripts auto-adapt via [`scripts/runtime-compose.sh`](../scripts/runtime-compose.sh) and the cross-runtime verification suite [`scripts/verify-runtimes.sh`](../scripts/verify-runtimes.sh).

### Engine Feature Comparison

| Feature | Docker Compose (`docker`) | Podman Compose (`podman`) | Nerdctl Compose (`nerdctl`) |
| :--- | :--- | :--- | :--- |
| **Daemon Model** | Host `dockerd` service | Rootless user daemon / podman machine | Rootless `containerd` daemon |
| **Socket Path** | `/var/run/docker.sock` | `/run/user/$UID/podman/podman.sock` | `/run/user/$UID/containerd-rootless/containerd.sock` |
| **Compose Command** | `docker compose` | `podman compose` (or `podman-compose`) | `nerdctl compose` |
| **SELinux / Volume Flags** | Direct bind mounts | Mounts require `:z` / `:Z` flags | Standard bind mounts |
| **Kernel eBPF Probe** | Full eBPF access | Requires rootful Podman for modern eBPF | Requires rootful containerd for eBPF |

---

## 2. Runtime Installation & Setup Instructions

### A. Docker Compose (Standard Setup)

```bash
# 1. Verify Docker Engine & Compose plugin
docker version
docker compose version

# 2. Boot the stack in detached mode
docker compose up -d

# 3. Check running status
docker compose ps
```

### B. Podman Compose (Rootless Setup)

> [!TIP]
> Rootless Podman isolates container execution without root privileges. For kernel-level eBPF probes (Falco), run Falco via host binary or rootful Podman.

```bash
# 1. Enable rootless Podman socket
systemctl --user enable --now podman.socket

# 2. Set DOCKER_HOST for tool compatibility
export DOCKER_HOST="unix:///run/user/$(id -u)/podman/podman.sock"

# 3. Boot using Podman Compose
podman compose up -d

# 4. Verify containers
podman compose ps
```
*For complete Podman/Lima details, see [podman_and_lima.md](./podman_and_lima.md).*

### C. Nerdctl Compose (Containerd Setup)

```bash
# 1. Ensure rootless containerd daemon is active
containerd-rootless-setuptool.sh status

# 2. Boot using Nerdctl Compose
nerdctl compose up -d

# 3. Verify services
nerdctl compose ps
```

### D. Bare-Minimum Binary Tarball Pattern (Host/Edge Deployments)

For constrained edge devices or bare-metal servers where container engines incur unacceptable overhead, LocalObserve provides bare-binary tarball installation patterns for host-native execution:

- **Falco (v0.43.1)**: Installed via official binary archive (`download.falco.org`). See [falco-host-install.md](./falco-host-install.md).
  ```bash
  bash scripts/install-falco-system.sh
  ```
- **rsigma (v0.19.0)**: Timescale rust streaming Sigma detection daemon (`Taskfile.yml` task `install-rsigma`).
  ```bash
  task install-rsigma
  ```
- **event-generator (v0.12.0)**: Falcosecurity rule trigger utility (`Taskfile.yml` task `install-tools`).
  ```bash
  task install-tools
  ```

---

## 3. Resource Profiling & Auditing (RAM, CPU, Filesystem)

The LocalObserve container stack is engineered for a minimal resource footprint, enabling continuous security telemetry collection alongside standard host workloads.

### Microservice Resource Footprints (`docker stats` Benchmark)

| Microservice | Container Image | RAM Usage | Configured RAM Limit | CPU Baseline | Target Role |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **`rsigma`** | `ghcr.io/timescale/rsigma:0.19.0` | **6.1 MiB** | 128 MiB | < 0.1% | Streaming Sigma detection engine |
| **`falco`** | `falcosecurity/falco:0.43.1` | **98.5 MiB** | 512 MiB | ~ 10.0% | Kernel syscall & eBPF event stream |
| **`alert-receiver`** | `localobserve-webhook:latest` | **9.1 MiB** | 64 MiB | < 0.1% | Webhook receiver & alert file writer |
| **`otel-collector`** | `otel/opentelemetry-collector-contrib` | **125.7 MiB** | 512 MiB | ~ 1.5% | Log tailing, OTTL parsing & routing |
| **`osquery`** | `osquery/osquery:latest` | **35.1 MiB** | 256 MiB | ~ 0.3% | Host telemetry & live query tables |
| **`openobserve`** | `zinclabs/openobserve` | **267.5 MiB** | 1024 MiB | ~ 0.2% | Log indexing, UI & telemetry storage |
| **`goflow2`** | `netsampler/goflow2:latest` | **5.2 MiB** | 256 MiB | < 0.1% | NetFlow / IPFIX flow collector |
| **Total Stack** | *7 Microservices* | **~ 547 MiB** | **2.75 GiB** | **~ 12.0%** | **Full Security Observability Pipeline** |

### Filesystem & Storage Footprint

LocalObserve isolates persistent data under `./.data/` on the host:

```
.data/
├── alerts/             # Active alert JSON files (< 1 MB)
├── falco/              # Falco raw event log (events.jsonl, ~1.5 MB)
├── openobserve/        # OpenObserve index & data store (~187 MB)
├── osquery/            # osquery result logs (~13 MB)
└── threat-intel/       # Synchronized threat feeds (~1.7 MB)
```

**Total Host Disk Usage**: **~ 203 MB**.

---

## 4. End-to-End Alerting Setup & Desktop Integration

LocalObserve routes detections from runtime event logs down to native Linux desktop alerts:

```
┌─────────────────────────┐
│ Kernel / System Events │
│ (Falco & osquery)       │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ OpenTelemetry Collector │ (Filelog Tailing & OTTL Schema Mapping)
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ rsigma Detection Engine │ (Evaluates active Sigma rules in rules/sigma/active_rules/)
└───────────┬─────────────┘
            │ HTTP Webhook POST
            ▼
┌─────────────────────────┐
│ alert-receiver Service  │ (Creates JSON files in /var/log/alerts/)
└───────────┬─────────────┘
            │ Volume Mount (./.data/alerts/)
            ▼
┌─────────────────────────┐
│ Host Desktop Notifier   │ (tools/desktop_notifier.py calls /usr/bin/notify-send)
└─────────────────────────┘
```

### Setting Up Desktop Notifications

1. **Test Webhook Dispatch**:
   ```bash
   curl -s -X POST http://localhost:9000/hooks/security-alert-open \
     -H "Content-Type: application/json" \
     -d '{"alert_name":"Suspicious Namespace Unshare Command","severity":"high","description":"Unprivileged user executed unshare --user"}'
   ```

2. **Run One-Shot Visual Desktop Replay**:
   ```bash
   task notify-desktop-replay
   ```

3. **Run Continuous Live Notifier Daemon**:
   ```bash
   task notify-desktop
   ```

---

## 5. Troubleshooting & Debugging Reference Links

Use these workspace documentation resources for detailed diagnostics:

- 🛠️ **[Troubleshooting Guide](./troubleshooting.md)**: Common service startup failures, port conflict resolution, and container engine diagnostics.
- 📜 **[Logs & Telemetry Reference](./logs.md)**: Event formats, OTel Collector OTTL transformations, and log paths.
- 🦅 **[Falco Host Installation Guide](./falco-host-install.md)**: Host-native binary installation, eBPF driver configuration, and validation.
- 🦭 **[Podman & Lima Setup Guide](./podman_and_lima.md)**: Rootless container configuration, CNI networking, and socket configuration.
- 🚀 **[Deployment Architecture Guide](./deployment.md)**: Full stack deployment instructions and security hardening.
- 🧪 **[Testing Harnesses Reference](./test-harnesses.md)**: Integration test suites, harness commands, and acceptance testing.
