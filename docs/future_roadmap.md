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

### 3. Magika AI File-Type Profiling
**Current State:** Magika exists in the repository (`README_MAGIKA.md`) but is not actively blocking or filtering scans.
**Action:**
- Implement a pre-scan hook: use Magika's deep-learning model to rapidly identify file types. 
- Whitelist benign media files (e.g., generic `.mp4`, `.png`) from heavy ClamAV scanning to drastically reduce CPU overhead during full-system sweeps.

---

## Phase 3: Active Response & Remediation

### 1. Automated Incident Response (SOAR capabilities)
**Current State:** OpenObserve aggregates data and fires alerts (webhooks/Slack). No automated action is taken against the threat.
**Action:**
- Implement Falco's *Falcosidekick* or a custom lightweight webhook listener.
- Create automated response playbooks:
  - **Isolate:** If Falco detects a container escape (e.g., execution of `nsenter`), automatically pause the Docker container or remove its networking namespace.
  - **Kill:** If ClamAV finds malware executing in `/tmp`, automatically kill the parent process tree via `kill -9`.
  - **Ban:** If Falco detects repeated outbound SSH attempts from `www-data` (T1021.004), automatically update `iptables` to block the destination IP.

### 2. Advanced eBPF Networking
**Current State:** Falco monitors syscalls primarily, and OSquery captures point-in-time network sockets.
**Action:**
- Refactor the Falco deployment to fully utilize its modern eBPF probe (instead of the kernel module).
- Integrate finer-grained network telemetry to capture full DNS request/response payloads and precise byte-counts for exfiltration detection without full packet capture overhead.
