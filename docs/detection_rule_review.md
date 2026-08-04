# Detection Rule Review (#39)

Automated review of all detection rules across Falco, Sigma, osquery, and OpenObserve alerts.

**Date:** 2026-08-04  
**Scope:** `falco_rules.local.yaml`, `rules/persistence_techniques.yaml`, `rules/sigma/`, `osqueryd.conf`, `alerts/openobserve/alerts.json`

---

## Summary

| Metric | Value |
|---|---|
| Total Falco rules (standalone) | 34 (+ 3 overrides) |
| Total Persistence Falco rules | 23 |
| Total active Sigma rules | 1 |
| Total osquery scheduled queries | 42 |
| Total OpenObserve alerts | 21 |
| Unique MITRE technique IDs covered | 37 |
| Techniques with ≥2 tool coverage | 15 |

---

## Fixed in this Review

### 1. Sigma curation self-contradiction ❌→✅
`curated_rules.yaml` had `disabled_rules.tags: [experimental]` which matched the only active Sigma rule (`suspicious_unshare.yaml`, tagged `experimental`). The curation engine would compile zero rules. Fixed by commenting out `experimental` from disabled tags with a note to re-enable when upstream SigmaHQ sync is activated.

### 2. NOTICE-priority rules invisible in alert pipeline ❌→✅
The catch-all `Falco-High-Severity` alert query filtered on `priority IN ('Warning','Critical','Alert','Emergency')` — excluding `NOTICE`. Three persistence rules (`At Job Scheduling`, `Systemctl Enable by Non-Admin`, `User Account Creation`) use NOTICE priority and would never fire. Fixed by adding `'Notice'` to the priority filter.

### 3. rsigma healthcheck ✅
Previously `exec: rsigma: not found` — binary is at `/rsigma`, not in PATH. Fixed in `docker-compose.yaml`.

---

## Known Issues (Documented, Not Fixed)

### 4. Near-duplicate Falco rules
Five pairs of rules detect the same technique with overlapping conditions:

| Technique | Rule 1 | Rule 2 | Recommendation |
|---|---|---|---|
| T1059.004 Reverse Shell | `Reverse Shell Detection` | `Reverse Shell Spawning` | Merge or differentiate by parent process |
| T1003.008 Shadow Read | `Shadow File Read by Non-Auth Process` | `Suspicious Read of etc shadow` | Merge — identical detection logic |
| T1574.006 LD_PRELOAD (local) | `Hijack Execution Flow with LD_PRELOAD` | `Dynamic Linker Hijacking via LD_PRELOAD` | Merge local rules |
| T1036 Masquerading | `Masquerading as Kernel Thread` | `System Utility Masquerading` | Merge — same condition pattern |
| T1574.006 LD_PRELOAD (persist) | `LD_PRELOAD Execution` | `Dynamic Linker Hijacking via LD_PRELOAD` | Consolidate across files |

**Recommendation:** Consolidate in a future PR. Merging these 10 rules into 5 would reduce alert noise without losing coverage.

### 5. Deprecated MITRE tag T1068
Rules #1–3 in `falco_rules.local.yaml` use `T1068` which was deprecated in MITRE ATT&CK v9. Should be updated to sub-technique IDs (T1068.002, etc.).

### 6. Sigma pipeline underpopulated
Only 1 Sigma rule is active. The upstream `sigma_hq_linux` ruleset (hundreds of Linux rules) is configured but disabled. Enable after evaluating false positive rates.

### 7. Only 17 of 42 osquery queries have MITRE tags in descriptions
Remaining 25 queries need MITRE technique annotations for coverage analysis.

---

## Coverage Gaps

High-value Linux techniques with **zero coverage** across all tools:

| MITRE ID | Technique | Priority |
|---|---|---|
| T1569.002 | Service Execution (systemd-run) | High |
| T1210 | Exploitation of Remote Services | High |
| T1562.004 | Disable System Firewall | Medium |
| T1546.008 | Accessibility Features backdoor | Medium |
| T1059.006 | Python/scripting execution | Medium |
| T1496 | Resource Hijacking (crypto mining) | Medium |

---

## Multi-Layer Coverage (Strong)

These techniques have ≥2 independent detection surfaces — the project's strongest defensive posture:

| MITRE Technique | Falco | Persist-Falco | osquery | Tools |
|---|---|---|---|---|
| T1053.003 Cron | ✅ | ✅✅ | ✅✅ | 3 |
| T1098.004 SSH Keys | ✅ | ✅✅✅ | ✅ | 3 |
| T1546.004 Shell Profile | ✅ | ✅✅ | ✅ | 3 |
| T1548.001 Setuid | ✅ | ✅✅✅ | ✅✅ | 3 |
| T1543.002 Systemd | — | ✅✅✅✅ | ✅ | 2 |
| T1071 C2 | ✅ | — | ✅ | 2 |
| T1036 Masquerading | ✅✅✅ | — | ✅ | 2 |
| T1548.003 Sudo | ✅ | — | ✅ | 2 |
| T1136.001 Create Account | — | ✅✅ | ✅ | 2 |
| T1070.003 Clear Logs | ✅ | — | ✅ | 2 |
| T1574.006 LD_PRELOAD | ✅✅ | ✅✅✅✅ | — | 2 |
| T1021.004 SSH Lateral | ✅✅ | — | — | 1* |
| T1562.001 Disable Tools | ✅✅ | — | — | 1* |
| T1003.008 Shadow Dump | ✅✅ | — | — | 1* |
| T1059.004 Unix Shell | ✅✅✅✅ | — | — | 1* |

\* Single-tool but multiple rules within that tool.
