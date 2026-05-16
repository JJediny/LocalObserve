# Optimization & Refactoring Plan

## 1. Current System Metrics Analysis
Based on `docker stats` and Loki metrics, the system operates efficiently but exhibits optimization opportunities:
*   **Loki Write Node**: High baseline memory (264MB) and CPU usage (5-6%) compared to other nodes due to high indexing volume and burst limits.
*   **Alloy Node**: Modest CPU but high memory footprint (294MB) due to internal caching and high frequency file tailing.
*   **Nginx Gateway**: Efficient (36MB memory, near 0% CPU), but previously bottlenecked by default buffering limits.

## 2. Refactoring Plan for Verbose Logging
Currently, certain high-frequency queries and raw logs bypass deduplication.

*   **Reduce OSQuery Spam**: 
    *   Change `process_open_sockets` and `processes` queries to use `diff` logging instead of `snapshot` logging. This forces osquery to only output *changes* rather than dumping the full table on every interval, drastically cutting ingestion volume.
    *   Increase the intervals of non-volatile queries (e.g., `rpm_packages`, `users`) from 1800s to 86400s (24 hours).
*   **Drop Verbose Journald Logs**: 
    *   Update `alloy-local-config.yaml` with a `loki.process` stage to aggressively drop debug and info-level systemd logs unless they originate from critical services (e.g., `sshd`, `sudo`, `docker`).

## 3. CPU and Memory Optimization Plan
*   **Loki Chunking and Compaction**:
    *   Modify `chunk_target_size` in `loki-config.yaml` from default (1MB) to 1.5MB to reduce CPU overhead spent on chunk flushing.
    *   Enable `max_chunk_age: 2h` to allow Loki to hold data in memory longer before flushing to MinIO, reducing I/O.
*   **Alloy Memory Profiling**:
    *   Implement `GOMEMLIMIT` environment variables for the Alloy container. Right now, it logs `memory is not limited, skipping`, which could lead to OOM kills if log bursts occur.
*   **Docker Container Limits**:
    *   Refactor `docker-compose.yaml` to enforce hard memory limits (e.g., `mem_limit: 512m`) on Loki containers, ensuring the host is never starved by unexpected log spikes.
