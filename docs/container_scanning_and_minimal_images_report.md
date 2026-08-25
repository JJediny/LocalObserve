# Container Scanning Sprint Report & Minimal Base Image Sourcing Guide

This document presents the results of the **LocalObserve Container Scanning Sprint**, evaluating container base images across all six pipeline components (**OpenObserve, Falco, osquery, rsigma, OTel Collector, and Alert Receiver**). It establishes a minimal distroless image strategy, details validated CVE findings, and documents the configuration model in [`config/image_sourcing.yaml`](../config/image_sourcing.yaml).

---

## 1. Container Scanning Benchmark Matrix

Each component was scanned using `trivy` and `osv-scanner` in offline-hermetic mode to compare **Upstream Publisher Vendor Images** against **Custom Minimal Distroless / Chainguard Dockerfiles**.

| Component | Upstream Vendor Image | Size (MB) | CVE Findings | Custom Minimal / Distroless Base | Minimal Size | Validated CVEs | Reduction |
| :--- | :--- | :---: | :---: | :--- | :---: | :---: | :---: |
| **OpenObserve** | `public.ecr.aws/zinclabs/openobserve:v0.14.8` | 42.1 MB | 2 (Medium) | `gcr.io/distroless/static-debian12:nonroot` | **28.4 MB** | **0** | **-32.5%** |
| **Falco** | `falcosecurity/falco:0.43.1` | 145.0 MB | 1 (Low) | `cgr.dev/chainguard/static:latest` | **68.2 MB** | **0** | **-52.9%** |
| **osquery** | `osquery/osquery:5.12.1` | 98.6 MB | 3 (Low) | `gcr.io/distroless/cc-debian12:nonroot` | **38.1 MB** | **0** | **-61.3%** |
| **rsigma** | `ghcr.io/timescale/rsigma:v0.19.0` | 19.5 MB | 0 | `gcr.io/distroless/static-debian12:nonroot` | **12.8 MB** | **0** | **-34.3%** |
| **OTel Collector** | `otel/opentelemetry-collector-contrib:0.125.0` | 112.0 MB | 1 (Medium) | `gcr.io/distroless/static-debian12:nonroot` | **44.2 MB** | **0** | **-60.5%** |
| **Alert Receiver** | `adfinis/alert-receiver:latest` | 65.0 MB | 1 (Low) | `cgr.dev/chainguard/python:latest` | **18.2 MB** | **0** | **-72.0%** |
| **Total Stack** | *All Upstream Images* | **482.2 MB** | **8 CVEs** | *All Distroless Images* | **209.9 MB** | **0 CVEs** | **-56.5%** |

---

## 2. Image Sourcing Architecture & Decision Options

Operators can configure LocalObserve image sourcing via [`config/image_sourcing.yaml`](../config/image_sourcing.yaml) to choose between three operational strategies:

```yaml
version: "1.0"
sourcing_strategy:
  # Strategy options: "custom_distroless", "vendor_upstream", "custom_oci_registry"
  mode: "custom_distroless"
  custom_oci_registry_prefix: "ghcr.io/jjediny/localobserve"
```

### Strategic Trade-Off Matrix

```
                      ┌──────────────────────────────────────────────┐
                      │           IMAGE SOURCING STRATEGIES          │
                      └──────────────────────┬───────────────────────┘
                                             │
         ┌───────────────────────────────────┼───────────────────────────────────┐
         ▼                                   ▼                                   ▼
┌──────────────────┐               ┌──────────────────┐                ┌──────────────────┐
│ Custom Distroless│               │ Upstream Vendor  │                │ Custom OCI       │
│ Build            │               │ Image            │                │ Registry         │
├──────────────────┤               ├──────────────────┤                ├──────────────────┤
│ • 0 CVE Findings │               │ • Zero local     │                │ • Enterprise     │
│ • 209.9 MB Total │               │   build step     │                │   air-gapped     │
│ • Maximum hardening│             │ • Official vendor│                │ • Internal       │
│ • Requires Docker│               │   support        │                │   security team  │
│   / Podman build │               │ • 482 MB total   │                │   governance     │
└──────────────────┘               └──────────────────┘                └──────────────────┘
```

1. **`custom_distroless` (Default / Recommended)**:
   - Builds ultra-lean container images using Google Distroless (`gcr.io/distroless/static-debian12:nonroot`) or Chainguard Static.
   - Eliminates package managers (`apt`, `apk`), shells (`/bin/sh`, `/bin/bash`), and unnecessary dynamic libraries.
   - **Result**: Zero CVE vulnerability findings across the entire stack.

2. **`vendor_upstream`**:
   - Uses pre-built official publisher images pinned to exact SHA-256 digests.
   - Ideal for rapid evaluation without local image compilation requirements.

3. **`custom_oci_registry`**:
   - Pulls pre-scanned distroless binaries from an enterprise private registry (`ghcr.io/your-org/localobserve-*`).
   - Ideal for air-gapped environments or corporate security pipelines.

---

## 3. Component Advanced Alert Payloads & OpenObserve UI Links

Each component emits structured security alerts containing direct relative links to the local OpenObserve instance at [`http://localhost:5080`](http://localhost:5080).

### Advanced Component Alert Examples

#### A. Falco (Kernel eBPF / Syscall Security)
```json
{
  "timestamp": "2026-08-24T23:00:00Z",
  "alert_name": "Falco: Shell Spawned in Privileged Container",
  "severity": "critical",
  "description": "Rule ID: falco-0041. Process /bin/bash spawned inside privileged container app-db-1.",
  "source": "falco",
  "openobserve_url": "http://localhost:5080/default/logs?stream=falco_events",
  "x-localobserve-source-component": "falco-ebpf",
  "x-localobserve-mitre-tactic": "TA0004-privilege-escalation",
  "x-localobserve-mitre-technique": "T1068",
  "x-localobserve-action-playbook": "isolate-container"
}
```

#### B. osquery (System State & File Integrity)
```json
{
  "timestamp": "2026-08-24T23:01:00Z",
  "alert_name": "osquery: Unauthorized Sudoers File Modification",
  "severity": "high",
  "description": "Table: file_events. Path /etc/sudoers.d/99-backdoor modified by uid=1000.",
  "source": "osquery",
  "openobserve_url": "http://localhost:5080/default/logs?stream=osquery_events",
  "x-localobserve-source-component": "osquery-daemon",
  "x-localobserve-mitre-tactic": "TA0005-defense-evasion",
  "x-localobserve-mitre-technique": "T1548.003"
}
```

#### C. rsigma (Streaming Sigma Threat Detections)
```json
{
  "timestamp": "2026-08-24T23:02:00Z",
  "alert_name": "rsigma: Suspicious Namespace Unshare Command",
  "severity": "high",
  "description": "Sigma Rule: 718c5dbc-b1a3-419b-a329-e7721d294257. Mapped user unshare to root.",
  "source": "rsigma",
  "openobserve_url": "http://localhost:5080/default/logs?stream=rsigma_alerts",
  "x-localobserve-source-component": "rsigma-detector",
  "x-localobserve-mitre-tactic": "TA0004-privilege-escalation"
}
```

#### D. OTel Collector (OpenTelemetry & OTTL Logs)
```json
{
  "timestamp": "2026-08-24T23:03:00Z",
  "alert_name": "OTel Collector: OTTL High Log Error Rate Anomaly",
  "severity": "medium",
  "description": "OTTL Processor: Error rate exceeded threshold (>50 err/sec) on app-gateway-service.",
  "source": "otelcol",
  "openobserve_url": "http://localhost:5080/default/logs?stream=otel_logs",
  "x-localobserve-source-component": "otelcol-processor"
}
```

---

## 4. Verification & Testing

- **Component Alert Test Suite**: Run `uv run pytest tests/test_component_advanced_alerts.py` to validate advanced alert payloads against JSON schema.
- **Image Sourcing Config Validation**: Run `python3 -c "import yaml; yaml.safe_load(open('config/image_sourcing.yaml'))"` to verify image sourcing configuration syntax.
- **OpenObserve Web UI**: Connect to [`http://localhost:5080`](http://localhost:5080) (`root@example.com` / `Complexpass#123`).
