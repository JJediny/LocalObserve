# MITRE ATT&CK for Linux: Telemetry & Detection Coverage

Based on the telemetry provided by our integrated OSquery configuration (`osqueryd.conf`), Falco rules (`falco_rules.local.yaml`), and ClamAV integrations, we have closed all previously identified Linux coverage gaps.

This document serves as the system record for our **MITRE ATT&CK Linux Detection Coverage** posture, showing each technique, its active detection capability, and implementation mechanism.

---

## 🛡️ Active Detections & Implementation Status

All identified coverage gaps have been **[FULLY RESOLVED]** and integrated into our real-time monitoring and scheduled query pipelines.

| MITRE ID | Technique Name | Status | Detection Mechanism | Configuration / Rule |
| :--- | :--- | :--- | :--- | :--- |
| **T1021.004** | Remote Services: SSH | **Resolved** | Real-Time (Falco) | `Suspicious Outbound SSH Connection` |
| **T1059.004** | Command and Scripting: Unix Shell | **Resolved** | Real-Time (Falco) | `Reverse Shell Spawning` |
| **T1546.004** | Event Triggered Execution: `.bashrc` | **Resolved** | Real-Time + FIM | `User Profile Bashrc Modification` / OSquery FIM |
| **T1574.006** | Hijack Execution Flow: `LD_PRELOAD` | **Resolved** | Real-Time (Falco) | `Dynamic Linker Hijacking via LD_PRELOAD` |
| **T1037.004** | Boot Initialization Scripts | **Resolved** | FIM (OSquery) | `bash_profiles` & `init_scripts` blocks |
| **T1070.003** | Clear Command History | **Resolved** | Real-Time (Falco) | `Truncate Command History` |
| **T1036.003** | Masquerading: Fake Kernel Threads | **Resolved** | Real-Time (Falco) | `System Utility Masquerading` |
| **T1552.003** | Unsecured Credentials: Bash History | **Resolved** | Real-Time (Falco) | `Unauthorized Access to User Bash History` |
| **T1003.008** | OS Credential Dumping: `/etc/shadow` | **Resolved** | Real-Time (Falco) | `Suspicious Read of etc shadow` |
| **T1036** | Masquerading: Ownerless Processes | **Resolved** | Scheduled + Real-Time | `ownerless_processes` (OSquery) & `Process Executed by Invalid User` (Falco) |

---

## 🔍 Implementation Details

### 1. Execution & Lateral Movement

#### **[T1021.004] Remote Services: SSH**
* **Status**: **Active**
* **Falco Rule**: `Suspicious Outbound SSH Connection`
* **Trigger**: Detects outbound SSH/SCP execution originating from unexpected service daemons (e.g., `www-data`, `postgres`, `mysql`, `redis`, `daemon`) or web-server parents.

#### **[T1059.004] Command and Scripting Interpreter: Unix Shell**
* **Status**: **Active**
* **Falco Rule**: `Reverse Shell Spawning`
* **Trigger**: Detects shell spawning (`bash`, `sh`, `dash`, `zsh`) associated with active network sockets or spawned by command tools (`nc`, `netcat`, `ncat`, `python`, `perl`, `ruby`, `php`).

---

### 2. Persistence & Privilege Escalation

#### **[T1546.004] Event Triggered Execution: `.bash_profile` and `.bashrc`**
* **Status**: **Active**
* **OSquery FIM**: Monitors user and root bash profile modifications:
  * `/home/%/.bashrc`, `/home/%/.bash_profile`
  * `/root/.bashrc`, `/root/.bash_profile`
* **Falco Rule**: `User Profile Bashrc Modification` (alerts on profile modification by unauthorized binaries).

#### **[T1574.006] Hijack Execution Flow: Dynamic Linker Hijacking (`LD_PRELOAD`)**
* **Status**: **Active**
* **Falco Rule**: `Dynamic Linker Hijacking via LD_PRELOAD`
* **Trigger**: Triggers immediately when a spawned process contains `LD_PRELOAD=` in its environment parameters.

#### **[T1037.004] Boot or Logon Initialization Scripts**
* **Status**: **Active**
* **OSquery FIM**: Actively tracks integrity changes to:
  * `/etc/rc.local`
  * `/etc/init.d/%%` (SysV init scripts)

---

### 3. Defense Evasion & Masquerading

#### **[T1070.003] Indicator Removal on Host: Clear Command History**
* **Status**: **Active**
* **Falco Rule**: `Truncate Command History`
* **Trigger**: Detects truncation of `.bash_history` (writing file with size `0`).

#### **[T1036.003] Masquerading: Fake Kernel Threads**
* **Status**: **Active**
* **Falco Rule**: `System Utility Masquerading`
* **Trigger**: Detects user-space processes masquerading as kernel threads (e.g., starting with `kworker/` or `rcu_sched` but residing outside the `/kernel/` path).

#### **[T1036] Masquerading: Ownerless & Invalid Processes**
* **Status**: **Active**
* **Falco Rule**: `Process Executed by Invalid User` (Alerts on process spawned under an invalid/non-existent UID, where username = `<NA>`).
* **OSquery scheduled query**: `ownerless_processes`
  ```sql
  SELECT p.pid, p.name, p.path, p.cmdline, p.uid, p.gid FROM processes p LEFT JOIN users u ON p.uid = u.uid WHERE u.uid IS NULL LIMIT 100;
  ```

---

### 4. Credential Access

#### **[T1552.003] Unsecured Credentials: Bash History**
* **Status**: **Active**
* **Falco Rule**: `Unauthorized Access to User Bash History`
* **Trigger**: Detects non-root users reading bash history files belonging to other users (`user.uid != fd.uid`).

#### **[T1003.008] OS Credential Dumping: `/etc/shadow`**
* **Status**: **Active**
* **Falco Rule**: `Suspicious Read of etc shadow`
* **Trigger**: Triggers on unauthorized read operations on `/etc/shadow` by unexpected processes (whitelisting only `sshd`, `sudo`, `su`, `passwd`, `osqueryd`, etc.).
