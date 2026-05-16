# Loki Security Infrastructure

A complete, automated log aggregation and security monitoring solution leveraging Grafana Loki, Alloy, Falco, osquery, and OpenObserve.

## Setup Instructions

This repository is fully containerized and runs on Docker. 

### 1. Start the Stack
To start the core services (Loki, Grafana, Alloy, Falco) along with the optional OpenObserve profile, run:
```bash
docker compose --profile openobserve up -d
```

*Note: If you are using Rancher Desktop or a custom Docker socket path, you can map it via environment variables before running:*
```bash
DOCKER_SOCKET=/home/john/.docker/desktop/docker.sock docker compose --profile openobserve up -d
```

### 2. Verify Security Infrastructure (Test Harnesses)
We use `go-task` and specific Go binaries to validate our `osquery` and `falco` deployments against real schemas and kernel calls.

Run the test suite to validate your deployment:
```bash
task test
```

Individual harness commands:
*   `task test-osquery`: Dry-runs all scheduled osquery rules against local schemas using `osqtool`.
*   `task test-falco`: Executes live kernel calls using `event-generator` to ensure Falco probes are successfully capturing threats.

---

## Localhost Navigation & Access

Once the stack is running, you can access the various web interfaces at the following local URLs:

### Grafana (Visualization & Exploration)
*   **URL:** [http://localhost:3000](http://localhost:3000)
*   **Username:** `admin`
*   **Password:** `admin`
*   *Note: The Loki datasource is automatically provisioned and ready for use in the "Explore" tab.*

### OpenObserve (Alternative Observability Platform)
*   **URL:** [http://localhost:5080](http://localhost:5080)
*   **Username:** `root@example.com`
*   **Password:** `Complexpass#123`

### MinIO (S3 Object Storage for Loki)
*   **URL:** [http://localhost:9000](http://localhost:9000) (API) / [http://localhost:9001](http://localhost:9001) (Console)
*   **Username:** `loki`
*   **Password:** `supersecret`

---

## Documentation Index

The root documentation has been condensed and organized into the `/docs` folder for focused reading:

*   **[Setup & Deployment (`/docs/deployment.md`)](./docs/deployment.md)**: Architectural overview and full deployment procedures.
*   **[Quickstart (`/docs/quickstart.md`)](./docs/quickstart.md)**: Step-by-step 60-second guide for first-time setup.
*   **[Test Harnesses (`/docs/test-harnesses.md`)](./docs/test-harnesses.md)**: Detailed breakdown of `osqtool` and `event-generator` CI/CD integration.
*   **[osquery (`/docs/osquery.md`)](./docs/osquery.md)**: Configuration details, table schemas, and forensic profiling.
*   **[Logs & Sources (`/docs/logs.md`)](./docs/logs.md)**: Log aggregation patterns and Alloy syslog ingestion.
*   **[CISA KEV Coverage (`/docs/cisa-kev.md`)](./docs/cisa-kev.md)**: Exploit threat-hunting coverage using Falco and osquery.
*   **[Performance Optimization (`/docs/optimization.md`)](./docs/optimization.md)**: Lowering CPU/Disk I/O impact and SSD tuning.
*   **[Benchmarks (`/docs/benchmarks.md`)](./docs/benchmarks.md)**: Performance comparisons and ingestion limits.
*   **[Security Policy (`/docs/security.md`)](./docs/security.md)**: Threat models and access isolation.
*   **[Commands Reference (`/docs/commands.md`)](./docs/commands.md)**: Common CLI utilities for daily operation.
*   **[Troubleshooting (`/docs/troubleshooting.md`)](./docs/troubleshooting.md)**: Fixes for common networking, locking, or resource issues.
