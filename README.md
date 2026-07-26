# Security Observability & Threat Detection Pipeline

A complete, high-performance, and automated security monitoring solution leveraging **Falco**, **OSquery**, **ClamAV**, and **OpenObserve**.

> **Architecture Note:** This project originally evaluated Grafana, Loki, and Alloy for telemetry aggregation. After rigorous benchmarking and usability testing, we determined to proceed exclusively with **OpenObserve** and the **OpenTelemetry (OTEL) Collector** due to its superior performance, unified analytics, and native VRL parsing capabilities. Legacy Loki configurations have been archived to `docker-compose.loki.yaml` for reference.

## Components & Technologies In Use

This pipeline leverages the following open-source security and observability tools:

- **[OpenObserve](https://openobserve.ai/)** — Cloud-native, high-performance observability platform for logs, metrics, traces, and dashboards.
- **[Timescale RSigma](https://rsigma.io/)** — Fast, edge-based Sigma detection engine for real-time log analysis and webhook alerting.
- **[OpenTelemetry Collector Contrib](https://github.com/open-telemetry/opentelemetry-collector-contrib)** — High-performance log and metrics agent/gateway for flattening, parsing, and routing telemetry.
- **[Falco](https://falco.org/)** — Cloud-native runtime security tool for kernel syscall behavior analysis.
- **[OSquery](https://osquery.io/)** — SQL-powered operating system instrumentation, monitoring, and state querying.
- **[GoFlow2](https://github.com/netsampler/goflow2)** — NetFlow/sFlow/IPFIX collector for network traffic telemetry.
- **[Google Magika](https://github.com/google/magika)** — AI-powered file type classification system used for pre-scanning binaries.
- **[ClamAV](https://www.clamav.net/)** — Open-source antivirus engine and YARA scanning daemon.
- **[Docker](https://www.docker.com/)** / **[Podman](https://podman.io/)** / **[Nerdctl](https://github.com/containerd/nerdctl)** — Container engines and compose orchestration runtimes.

## Features

- **Kernel-Level Behavioral Analysis:** Powered by **Falco**, monitoring syscalls for container escapes, rootkits, and privilege escalation.
- **Deep System Telemetry & FIM:** Powered by **OSquery**, actively hunting for persistence mechanisms, unauthorized SSH keys, and modifying critical system files (`.bashrc`, `/etc/shadow`).
- **Signature & YARA Threat Intel:** Powered by **ClamAV**, synchronized dynamically with MalwareBazaar/Abuse.ch community YARA rules to detect active malware campaigns and staging scripts.
- **AI Hardware Monitoring:** Integrated **NVIDIA DCGM Exporter** to observe GPU telemetry for AI workload anomalies.
- **MITRE ATT&CK Mapping:** Automated alignment of security events to the MITRE STIX JSON framework via OpenObserve Enrichment Tables.
- **Infrastructure as Code:** Taskfile-driven automation for testing rules (`osqtool`), updating signatures, and bi-directional syncing of dashboards.

## Setup Instructions

This repository is fully containerized and supports standard container engines (**Docker**, **Podman**, and **Nerdctl**).

### 1. Start the Core Security Stack
You can start the core stack using your preferred container tool:

#### Using Docker Compose:
```bash
docker compose up -d
```

#### Using Podman Compose:
```bash
podman-compose up -d
# Or:
podman compose up -d
```

#### Using Nerdctl Compose:
```bash
nerdctl compose up -d
```

To enable on-demand ClamAV scanning as well, add the `--profile scan` flag (or `scan` profile equivalent in podman/nerdctl):
```bash
docker compose --profile scan up -d clamav clamav-scanner
```

### 2. Verify Security Infrastructure (Test Harnesses)
We use `go-task` to manage operations. Run the test suite to validate your deployment configurations against real schemas and kernel calls:
```bash
task test
```

For host-side emulation with CALDERA stockpile abilities plus OpenTelemetry trace verification:
```bash
task bootstrap-caldera
task list-safe-caldera-abilities
task test-host-emulation
```

Direct invocation uses the module form:
```bash
uv run python -m pytest tests/test_caldera_otel_integration.py --run-stack --run-host-emulation -v
```

To run a payload-backed safe ability directly:
```bash
uv run python tools/caldera_otel_harness.py run-ability --bootstrap --ability-id a0676fe1-cd52-482e-8dde-349b73f9aa69 --verify-trace
```

### 3. Sync Threat Intel & Dashboards
Pull the latest YARA rules and ensure your OpenObserve instance is hydrated with our custom dashboards:
```bash
task update-yara
task sync-oo-import
```

---

## Localhost Access

### OpenObserve (Unified Observability Platform)
*   **URL:** [http://localhost:5080](http://localhost:5080)
*   **Username:** `root@example.com`
*   **Password:** `Complexpass#123`

---

## Documentation Index

Detailed architectural decisions, tuning parameters, and setup guides are available in the `/docs` directory:

*   **[Deployment Guide](./docs/deployment.md)**: Architectural overview and full deployment procedures.
*   **[Podman & Lima Support](./docs/podman_and_lima.md)**: Deployment instructions and security configurations for rootless Podman and Lima.
*   **[Container Standardization & Sidecars](./docs/standardization_and_sidecars.md)**: Feasibility analysis of Distroless standardization and running privileged sidecars for osquery and Falco.
*   **[MITRE ATT&CK Enrichment](./docs/mitre_attack_stix_enrichment.md)**: Explanation of the STIX JSON lookup strategy and coverage analysis.
*   **[MITRE Coverage Gaps & Implementation](./docs/mitre_linux_coverage_gaps.md)**: Details on the Falco/OSquery rules actively closing Linux execution gaps.
*   **[Abuse.ch YARA Integration](./docs/abuse_ch_integration.md)**: Threat intelligence ingestion pipeline.
*   **[Future Roadmap & Refactoring](./docs/future_roadmap.md)**: Outstanding work and next phases of architecture development.
*   **[Test Harnesses](./docs/test-harnesses.md)**: Detailed breakdown of `osqtool` and `event-generator` integration.
*   **[Performance Optimization](./docs/optimization.md)**: Lowering CPU/Disk I/O impact and SSD tuning.


## Related Projects

Other open-source projects in the security observability and device management space worth exploring:

- **[Fleet](https://fleetdm.com)** — An open-source fleet management platform built on osquery that provides real-time visibility into endpoints (laptops, servers, containers). Fleet offers device hygiene policies, vulnerability management, and remote actions such as device wipe, making it a strong complement to kernel-level monitoring pipelines like this one. See also: [Protecting the Linux device: Remote wipe, USB, and sudo](https://fleetdm.com/articles/protecting-the-linux-device-remote-wipe-usb-sudo).
- **[Wazuh](https://wazuh.com)** — A free, open-source security monitoring platform that combines SIEM, XDR, and compliance capabilities. Wazuh provides log data analysis, intrusion detection, file integrity monitoring, and vulnerability detection across hosts and containers, and can be integrated alongside or as an alternative to the Falco/OSquery stack.
