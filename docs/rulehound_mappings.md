# Rulehound Detection Rules Alignment & Reference Mappings

[Rulehound](https://github.com/infosecB/Rulehound) is Brendan Chamberlain's catalog of public threat detection rules, indexing rulesets across **Sigma**, **Splunk**, **Elastic**, and **Panther**. 

This document serves as the integration matrix mapping Rulehound's core indexed Linux detection rulesets to the **LocalObserve** unified security telemetry pipeline (`falco_rules.local.yaml` and `osqueryd.conf`).

---

## 1. Core Reference Mapping Matrix

| Rulehound Rule ID / Name | MITRE ATT&CK Mapping | LocalObserve Telemetry Engine | LocalObserve Configuration Location | Telemetry Scope |
| :--- | :--- | :--- | :--- | :--- |
| **`lnx_shell_profiles_mod.yml`** (Sigma)<br/>*Shell Profiles Modification* | **T1546.004**<br/>Persistence: Unix Shell Config Modify | **Falco** & **OSquery (FIM)** | `User Profile Bashrc Modification` in `falco_rules.local.yaml`<br/>`bash_profiles` in `osqueryd.conf` | Captures writes to `~/.bashrc`, `/etc/profile`, `/etc/bash.bashrc` by unexpected processes. |
| **`lnx_systemd_service_creation.yml`** (Sigma)<br/>*Systemd Service Creation* | **T1543.002**<br/>Persistence: Systemd Service | **OSquery (FIM & SQL)** | `systemd_units` query & `systemd_configs` FIM in `osqueryd.conf` | Captures new unit file drop-ins in `/etc/systemd/system/` and monitors overall service state changes. |
| **`lnx_failed_sudo_executions.yml`** (Sigma)<br/>*Sudo Auditing / Failed Sudo* | **T1548.003**<br/>Privilege Escalation: Sudo | **Falco** | `Sudo Execution by Non-Admin` in `falco_rules.local.yaml` | Flags any elevated `sudo` commands invoked by service accounts or non-administrative logins. |
| **`lnx_usb_insertion_detect.yml`** (Elastic)<br/>*Physical USB Intrusion* | **T1200**<br/>Initial Access: Hardware Add | **OSquery (SQL)** | `usb_devices` scheduled query in `osqueryd.conf` | Polls connected hardware buses for new vendor/product IDs to capture unauthorized mass storage drives. |
| **`lnx_destructive_shred_erase.yml`** (Sigma)<br/>*Destructive Wipes / Wiping* | **T1485**<br/>Impact: Data Destruction | **Falco** | `Secure Erase or Destructive Disk Wiping` in `falco_rules.local.yaml` | Triggers high-priority alerts on physical disk wiping attempts (`shred` or raw block output redirects via `dd`). |
| **`lnx_ssh_authorized_keys_mod.yml`** (Sigma)<br/>*SSH Authorized Keys Edit* | **T1098.004**<br/>Persistence: SSH Authorized Keys | **Falco** & **OSquery (FIM)** | `Unauthorized SSH Authorized Keys Modification` in `falco_rules.local.yaml`<br/>`ssh_keys` in `osqueryd.conf` | Alerts on unauthorized modifications or writes to `authorized_keys` stores by non-admin processes. |
| **`lnx_udev_rules_mod.yml`** (Elastic)<br/>*Udev Rules Backdoor* | **T1098**<br/>Persistence: Account / System Backdoors | **Falco** & **OSquery (FIM)** | `Unauthorized Udev Rules Modification` in `falco_rules.local.yaml`<br/>`udev_rules` in `osqueryd.conf` | Captures persistent configuration drops in `/etc/udev/rules.d/` mapping to physical endpoint escapes. |
| **`lnx_motd_backdoor_mod.yml`** (Sigma)<br/>*MOTD Message Backdoors* | **T1037**<br/>Persistence: Boot/Logon Initialization Scripts | **Falco** & **OSquery (FIM)** | `Message of the Day MOTD Modification` in `falco_rules.local.yaml`<br/>`motd_scripts` in `osqueryd.conf` | Monitors the `/etc/update-motd.d/` directory for persistent executable script drops. |

---

## 2. Programmatic Ingestion Blueprint

To extend this pipeline dynamically with community rule updates from Rulehound (Sigma Linux catalog), we utilize a standard JSON/YAML rule translation architecture:

```
[Sigma Rule (Rulehound)] 
         │
         ▼
[scripts/import_rulehound_mappings.py] ── Translates attributes
         │
         ├─► [Falco Rules Appends (Modern eBPF syscall patterns)]
         └─► [OSquery Packs (SQL scheduler / FIM targets)]
```

### Sigma-to-Falco Translation Logic:
*   **Process Creation (`action: global`)**: Mapped to Falco's `spawned_process` and `proc.name`/`proc.cmdline` checks.
*   **File Modifications (`action: file_write`)**: Mapped to Falco's `open_write` and `fd.name` checks.
*   **Network Activity (`action: outbound`)**: Mapped to Falco's `outbound` and `fd.rport`/`fd.rip` checks.

This structure allows the pipeline to remain dynamically aligned with the latest open-source threat intelligence catalogs without manually rewriting underlying detection logic.
