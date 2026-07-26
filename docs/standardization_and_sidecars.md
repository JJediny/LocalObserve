# Container Standardization & Privileged Sidecars Guide

This guide details the design decisions and instructions for:
1.  **Distroless Container Standardization:** An analysis of which containers can (and cannot) run on minimal Distroless images.
2.  **Privileged Sidecar Deployments:** Running `osqueryd` and `falco` inside privileged containers to capture host telemetry without local daemon dependencies.

---

## 1. Distroless Container Standardization Analysis

Distroless images contain only the application and its immediate runtime dependencies. They lack package managers (`apt`, `apk`), shells (`bash`, `sh`), and standard Unix utilities.

### Current Base Image Breakdown & Feasibility

| Service | Current Base | Can Standardize on Distroless? | Rationale & Constraints |
|---|---|---|---|
| **openobserve** | **Distroless** (Debian 13) |  **Yes (Standardized)** | Uses official `public.ecr.aws/zinclabs/openobserve`, which is pre-compiled and packaged on a Distroless base. |
| **otel-collector**| **Distroless/Scratch** |  **Yes (Standardized)** | Uses official `otel/opentelemetry-collector-contrib` which is natively built on a scratch/minimal base. |
| **goflow2** | **Alpine/Scratch** |  **Yes (Standardized)** | Natively runs on minimal alpine/scratch without shell utilities. |
| **falco** | **Debian** |  **No** | Requires dynamic linkers and utility programs to load or compile kernel probes/eBPF drivers on startup. |
| **osquery** | **Debian/Ubuntu** |  **No** | Dynamically interacts with various system APIs and requires a robust standard C library matching target platforms for kernel telemetry querying. |
| **dcgm-exporter** | **Ubuntu (NVIDIA)** |  **No** | Requires proprietary NVIDIA driver interaction wrappers, CUDA, and DCGM shared library hooks maintained upstream. |
| **clamav** | **Debian** |  **No** | Requires `freshclam` updater binaries, signature signature verification utilities, and write access to directories. |
| **alert-receiver**| **Alpine** |  **No** | Requires D-Bus tools, `notify-send`, `xhost`, and other GUI-adjacent utility scripts to trigger desktop alerts. |

### Conclusion on Standardization
The core routing and processing nodes (**OpenObserve**, **OTel Collector**, **GoFlow2**) are already standardized on minimal or Distroless bases. Upstream security and physical monitoring agents (**Falco**, **ClamAV**, **DCGM Exporter**, **Alert Receiver**) require low-level libraries, dynamic driver loading, or system commands, making Debian/Alpine necessary for runtime support.

---

## 2. Privileged Sidecar Configurations

Running monitoring daemons inside containers requires giving them full visibility into the host namespaces and hardware devices. This is achieved by running them as **privileged sidecar containers**.

### Configuration Parameters
To monitor the host system, both `falco` and `osquery` are configured with the following properties in `docker-compose.yaml`:

*   **`privileged: true`**: Grants container processes root access to host devices and system calls.
*   **`pid: host`**: Maps the host's PID namespace into the container, allowing the service to inspect all host processes.
*   **`network_mode: host`**: Maps the host's network interfaces directly to the container, exposing network metrics and sockets.
*   **Volume Mounts**:
    *   `/proc:/host/proc` or `/:/host:ro,rslave`: Maps host runtime interfaces into the container.

---

## 3. Running Containerized `osquery` and `falco`

Both services are fully configured in the root `docker-compose.yaml` to run containerized.

### Step 1: Prepare Local Configurations
The sidecar containers read their settings from configuration files bind-mounted from the repository:
*   `falco`: `./falco-config.yaml` and `./falco_rules.local.yaml`
*   `osquery`: `./osquery.flags` and `./osqueryd.conf`

### Step 2: Start the Sidecars
To start the privileged sidecars alongside the rest of the telemetry stack, run:
```bash
docker compose up -d osquery falco otel-collector openobserve
```
*(Or use `podman compose` / `podman-compose` if running under Podman).*

### Step 3: Telemetry Harvesting
1.  **Osquery** runs inside its container and writes host event records to its bind-mounted volume `/var/log/osquery/osqueryd.results.log` (mapped to `./.data/osquery` on the host).
2.  **Falco** runs in its container and writes alerts to `/var/log/falco/` (mapped to `./.data/falco`).
3.  **OTel Collector** acts as the harvester, tailing both logs locally and shipping them to the **OpenObserve** engine for querying and dashboard rendering.
