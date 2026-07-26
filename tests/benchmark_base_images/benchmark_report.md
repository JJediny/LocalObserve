# OpenObserve Container Base Image Benchmarking Report

## 1. Executive Summary

This report evaluates container base images for running OpenObserve, focusing on minimizing resource footprints, ensuring operational stability, and resolving compatibility blockers.

Our tests confirm that the prebuilt OpenObserve binary is dynamically linked and strictly requires **GLIBC 2.38+**. 

*   **Production Recommendation:** Continue using the official **Distroless (Debian 13-based)** image. It offers the smallest footprint (309.62 MB) and the highest security posture (zero shell tools, minimal attack surface).
*   **Debugging/Local Recommendation:** Use **Debian Trixie Slim** (`debian:trixie-slim`). It provides the necessary GLIBC 2.39 runtime with a moderate footprint (362.62 MB) and a full interactive shell (`bash`/`apt`) for local troubleshooting.

---

## 2. GLIBC Compatibility & Runtime Analysis

The OpenObserve binary utilizes C23 features and standard library improvements, creating strict requirements on the host `libc` version.

| Base Image | libc Provider | libc Version | Compatibility Status | Failure Root Cause |
|---|---|---|---|---|
| **Distroless (Official)** | GNU libc (glibc) | 2.39 (Debian 13) |  **Compatible** | N/A |
| **Alpine Linux** | musl libc | N/A |  **Incompatible** | Relocation errors; cannot resolve GLIBC symbols even with `gcompat` |
| **Debian 13 Slim (Trixie)** | GNU libc (glibc) | 2.39 |  **Compatible** | N/A |
| **Ubuntu 24.04 (Noble)** | GNU libc (glibc) | 2.39 |  **Compatible** | N/A |
| **UBI 9 Minimal (RHEL 9)** | GNU libc (glibc) | 2.34 |  **Incompatible** | Crashed with `GLIBC_2.38` / `GLIBC_2.39` not found |

---

## 3. Benchmarking Metrics Comparison

The following metrics were captured under a standardized benchmarking harness using Podman.

| Base Image | Built Image Size | Startup Latency | RSS Memory | Direct Exec Support |
|---|---|---|---|---|
| **Distroless (Official)** | **309.62 MB** | **961.00 ms** | 99.02 MB |  Yes (Binary only, no shell) |
| **Alpine Linux** | 293.53 MB | *FAILED* | N/A |  No |
| **Debian 13 Slim (Trixie)**| 362.62 MB | 1163.34 ms | **95.85 MB** |  Yes (Shell and package manager) |
| **Ubuntu 24.04 (Noble)** | 361.61 MB | 1170.31 ms | 94.82 MB |  Yes (Shell and package manager) |
| **UBI 9 Minimal** | 385.26 MB | *FAILED* | N/A |  No |

---

## 4. Size-vs-Operability Trade-offs

Choosing a base image involves balancing footprint and security against debugging utility:

1.  **Distroless (Official):**
    *   *Pros:* Smallest footprint (309.62 MB), zero-shell security (prevents post-exploitation command injection).
    *   *Cons:* Cannot run `podman exec -it <container> sh` to debug issues or inspect local configs.
2.  **Debian Trixie Slim:**
    *   *Pros:* Full interactive shell (`bash`), package manager (`apt-get`) to install debugging utilities (e.g. `curl`, `netstat`).
    *   *Cons:* Larger size (+53 MB overhead), slightly slower container startup (+200 ms).
3.  **Ubuntu 24.04:**
    *   Similar to Debian Trixie, but slightly larger base layer and longer build times.

---

## 5. Workarounds and Host Integration

### AppArmor Daemon Conflicts
During our run, we identified that host-level AppArmor configurations blocked Docker from sending termination signals to containers, resulting in zombie containers locking port `15080`. 

1.  **Workaround:** We successfully migrated our benchmark runner and container execution to **Podman** on port `25080`. Podman operates rootless and avoids system-wide Docker daemon AppArmor profiles.
2.  **Stopping Geonode:** Instructions for stopping legacy Geonode containers to release system resources have been integrated into the troubleshooting documentation.
3.  **Alternative Container Runtimes:** Comprehensive documentation for **Podman** and **Lima** has been added to `docs/podman_and_lima.md` and integrated into the deployment guides.
