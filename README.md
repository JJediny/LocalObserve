# Security Observability & Threat Detection Pipeline

A complete, high-performance, and automated security monitoring solution leveraging **Falco**, **OSquery**, **ClamAV**, and **OpenObserve**.

> **Architecture Note:** This project originally evaluated Grafana, Loki, and Alloy for telemetry aggregation. After rigorous benchmarking and usability testing, we determined to proceed exclusively with **OpenObserve** and the **OpenTelemetry (OTEL) Collector** due to its superior performance, unified analytics, and native VRL parsing capabilities. Legacy Loki configurations have been archived to `docker-compose.loki.yaml` for reference.

## Features

- **Kernel-Level Behavioral Analysis:** Powered by **Falco**, monitoring syscalls for container escapes, rootkits, and privilege escalation.
- **Deep System Telemetry & FIM:** Powered by **OSquery**, actively hunting for persistence mechanisms, unauthorized SSH keys, and modifying critical system files (`.bashrc`, `/etc/shadow`).
- **Signature & YARA Threat Intel:** Powered by **ClamAV**, synchronized dynamically with MalwareBazaar/Abuse.ch community YARA rules to detect active malware campaigns and staging scripts.
- **AI Hardware Monitoring:** Integrated **NVIDIA DCGM Exporter** to observe GPU telemetry for AI workload anomalies.
- **MITRE ATT&CK Mapping:** Automated alignment of security events to the MITRE STIX JSON framework via OpenObserve Enrichment Tables.
- **Infrastructure as Code:** Taskfile-driven automation for testing rules (`osqtool`), updating signatures, and bi-directional syncing of dashboards.

## Setup Instructions

This repository is fully containerized and optimized for Linux hosts.

### 1. Start the Core Security Stack
To start the core services (Falco, OpenObserve, OTEL Collector, ClamAV Daemons, and DCGM):
```bash
docker compose up -d
```

### 2. Verify Security Infrastructure (Test Harnesses)
We use `go-task` to manage operations. Run the test suite to validate your deployment configurations against real schemas and kernel calls:
```bash
task test
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
*   **[MITRE ATT&CK Enrichment](./docs/mitre_attack_stix_enrichment.md)**: Explanation of the STIX JSON lookup strategy and coverage analysis.
*   **[MITRE Coverage Gaps & Implementation](./docs/mitre_linux_coverage_gaps.md)**: Details on the Falco/OSquery rules actively closing Linux execution gaps.
*   **[Abuse.ch YARA Integration](./docs/abuse_ch_integration.md)**: Threat intelligence ingestion pipeline.
*   **[Future Roadmap & Refactoring](./docs/future_roadmap.md)**: Outstanding work and next phases of architecture development.
*   **[Test Harnesses](./docs/test-harnesses.md)**: Detailed breakdown of `osqtool` and `event-generator` integration.
*   **[Performance Optimization](./docs/optimization.md)**: Lowering CPU/Disk I/O impact and SSD tuning.
