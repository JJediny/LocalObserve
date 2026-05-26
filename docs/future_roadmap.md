# Future Roadmap & Refactoring Plan

While the current architecture establishes a high-performance, real-time security observability pipeline using Falco, OSquery, ClamAV, and OpenObserve, several areas remain ripe for enhancement, refactoring, and deeper integration. 

Below are the prioritized phases for future development.

## Phase 1: Automation & Infrastructure as Code (IaC)

### 1. Automated OpenObserve Alert Provisioning
**Current State:** Dashboards are synchronized bi-directionally via API scripts (`tools/oo-dashboards.sh`), but alerts require manual configuration inside the OpenObserve UI.
**Action:** 
- Map the OpenObserve REST API endpoints for `/alerts`.
- Expand the Taskfile commands (`sync-oo-export` / `sync-oo-import`) to fully serialize and deserialize Alert logic into JSON.
- Store these JSON definitions in `./alerts/openobserve/` to ensure full GitOps compliance.

### 2. CI/CD Pipeline Integration
**Current State:** `task test` validates osquery schemas locally via `osqtool` and Falco via `event-generator`.
**Action:**
- Migrate these test harnesses into GitHub Actions (or GitLab CI).
- Ensure that every Pull Request modifying `falco_rules.local.yaml` or `osqueryd.conf` automatically triggers a dry-run validation against the latest Ubuntu and Alpine base images.

---

## Phase 2: Enhanced Threat Intelligence

### 1. Expanded YARA Integrations
**Current State:** ClamAV automatically fetches and hot-reloads MalwareBazaar/Abuse.ch community YARA rules.
**Action:**
- Expand `tools/update_yara_rules.sh` to ingest additional critical repositories (e.g., Neo23x0's Signature base, CISA IOCs, Elastic Security YARA rules).
- Categorize YARA rules by threat level so OpenObserve can dynamically prioritize `FOUND` events based on rule origin.

### 2. OSquery YARA/FIM Alignment
**Current State:** OSquery performs FIM on `.bashrc`, `.bash_history`, and `/etc/shadow`.
**Action:**
- Map the newly downloaded YARA rules directory (`.data/osquery/yara`) directly into the OSquery `yara_events` table.
- Configure OSquery to automatically execute a YARA scan against any file that triggers a FIM creation or modification event in sensitive directories (e.g., `/tmp`, `/var/tmp`, `/dev/shm`).

---

## Phase 3: Active Response & Remediation

### 1. Falcosidekick — DONE
**Status:** DONE — Falcosidekick is deployed in `falco-config.yaml` (sidekick config block) and `docker-compose.loki.yaml` (falcosidekick service).
Falco alerts are forwarded to OpenObserve and webhook endpoints via Falcosidekick.

### 2. Modern eBPF Probe — DONE
**Status:** DONE — `falco-config.yaml` sets `engine.kind: modern_ebpf`, replacing the legacy kernel module with the modern eBPF probe for lower overhead and broader syscall coverage.

### 3. Remaining Phase 3 Work (Planned)
- **DNS Telemetry:** Integrate finer-grained network telemetry to capture full DNS request/response payloads via the modern eBPF probe without full packet capture overhead.
- **Exfiltration Detection:** Add precise byte-count tracking for outbound connections to identify data exfiltration patterns (e.g., large uploads from `www-data`).
- **Automated Response Playbooks:** Implement lightweight webhook-triggered playbooks for container isolation, process kill, and iptables banning in response to Falco alert severity levels.

---

## Phase 4 (Planned): Magika AI File-Type Pre-Scan Hook

**Status:** FUTURE WORK — not yet implemented. This phase is entirely planned and has no partial implementation in the current codebase.

**Goal:** Implement a Magika AI-based pre-scan hook that runs before ClamAV to rapidly identify file types using Google's deep-learning model.

**Action:**
- Before invoking ClamAV for a full scan, run Magika against the target file to determine its true content type (independent of file extension).
- Whitelist benign media files (e.g., generic `.mp4`, `.png`, `.jpg`) identified by Magika to skip heavy ClamAV scanning, drastically reducing CPU overhead during full-system sweeps.
- Integrate the hook into the existing ClamAV scan pipeline (`clamd` watch + `on_access` scanning).
- Emit a structured log event to OpenObserve for each pre-scan decision (allowed/scanned) for audit visibility.

Note: `README_MAGIKA.md` exists in the repository for reference but Magika is not currently active in any scan path.
