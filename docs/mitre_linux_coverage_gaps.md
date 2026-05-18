# MITRE ATT&CK for Linux: Coverage Gaps & Implementation Strategies

Based on the current telemetry provided by your OSquery configuration (`osqueryd.conf`), Falco rules (`falco_rules.local.yaml`), and ClamAV integrations, we have established a strong baseline for Persistence, Privilege Escalation, and Defense Evasion.

However, comparing our current tagging against the MITRE ATT&CK Matrix for Linux reveals several coverage gaps. Below is a prioritized list of relevant techniques that are **not yet implemented**, along with actionable suggestions for how to capture them.

---

## 1. Execution & Lateral Movement

### [T1021.004] Remote Services: SSH
Threat actors frequently leverage SSH for lateral movement between Linux hosts after obtaining credentials or keys.
* **Gap:** We monitor SSH keys for persistence, but we don't actively monitor outbound SSH connections originating from unexpected contexts.
* **Implementation Suggestion (Falco):** Create a rule that triggers when `proc.name = ssh` or `proc.name = scp` is executed by non-administrative users or by service accounts (e.g., `www-data`, `postgres`).

### [T1059.004] Command and Scripting Interpreter: Unix Shell
Adversaries use interactive shells to execute arbitrary commands.
* **Gap:** While we log process executions periodically in OSquery, we aren't alerting on suspicious shell spawning in real-time.
* **Implementation Suggestion (Falco):** Detect Reverse Shells by creating a rule that looks for shell binaries (`bash`, `sh`, `dash`) where `fd.type = ipv4` and `fd.connected = true`, or when shells are spawned by web-server daemon processes.

---

## 2. Persistence & Privilege Escalation

### [T1546.004] Event Triggered Execution: .bash_profile and .bashrc
Modifying user profiles ensures malware is executed automatically whenever a user logs in.
* **Gap:** OSquery monitors critical files like `/etc/passwd`, but user-level profile scripts are ignored.
* **Implementation Suggestion (OSquery):** Add an OSquery File Integrity Monitoring (FIM) block for `/home/*/.bashrc`, `/home/*/.bash_profile`, and `/root/.bashrc`.
* **Implementation Suggestion (Falco):** Alert on `open_write` events targeting `.bashrc` or `.profile` by non-owner processes.

### [T1574.006] Hijack Execution Flow: Dynamic Linker Hijacking (LD_PRELOAD)
Malware (such as user-land rootkits) often uses `LD_PRELOAD` to hook functions and hide files or network connections.
* **Gap:** We scan `process_envs` in OSquery every 3600 seconds, but this leaves a massive window for ephemeral processes to evade detection.
* **Implementation Suggestion (Falco):** Create a real-time rule using `evt.type = execve` where `proc.env` contains `LD_PRELOAD=`.

### [T1037.004] Boot or Logon Initialization Scripts: rc.common
Modifying `rc.local` or `init.d` scripts provides persistent, high-privileged execution at boot.
* **Gap:** We check `systemd_units`, but legacy SysV init scripts can still be abused.
* **Implementation Suggestion (OSquery):** Add `/etc/rc.local` and `/etc/init.d/*` to the OSquery FIM configuration.

---

## 3. Defense Evasion

### [T1070.003] Indicator Removal on Host: Clear Command History
Adversaries clear or disable bash history to hide their tracks.
* **Gap:** We have a Falco override for `rm` and `truncate`, but attackers often use `unset HISTFILE` or `history -c`.
* **Implementation Suggestion (Falco):** Falco cannot natively see `unset` (since it's a shell built-in without a syscall). However, we can detect truncation of `.bash_history` by looking for `open_write` events where the file is `.bash_history` and `fd.size = 0`.
* **Implementation Suggestion (OSquery):** Query `process_envs` for processes explicitly overriding `$HISTFILE` to `/dev/null`.

### [T1036.003] Masquerading: Rename System Utilities
Attackers rename malicious binaries to look like legitimate system tools (e.g., `kworker/u4:2`).
* **Gap:** We look for hidden processes (starting with `.`), but not renamed processes.
* **Implementation Suggestion (Falco):** Alert when a process name matches a kernel thread format (`kworker`, `rcu_sched`) but the executable path is in user-space (`/tmp`, `/dev/shm`, `/var/tmp`).

---

## 4. Credential Access

### [T1552.003] Unsecured Credentials: Bash History
Actors scrape `.bash_history` files for cleartext passwords accidentally typed by administrators.
* **Gap:** We do not detect access to other users' history files.
* **Implementation Suggestion (Falco):** Detect when a user reads `.bash_history` files located outside of their own home directory (e.g., `user.uid != fd.uid`).
* **Implementation Suggestion (ClamAV/YARA):** Use the newly implemented Abuse.ch YARA capability to scan `/home/*/.bash_history` for regex patterns matching high-value AWS keys or database connection strings.

### [T1003.008] OS Credential Dumping: /etc/shadow
Attackers read `/etc/shadow` to crack password hashes offline.
* **Gap:** We detect reads of kernel files, but not necessarily local credential files.
* **Implementation Suggestion (Falco):** Implement a strict rule alerting on `open_read` of `/etc/shadow` by any process other than expected authentication daemons (`sshd`, `sudo`, `su`, `passwd`).

---

## Next Steps for Implementation
To bring these into your environment:
1. Copy the **OSquery FIM** targets into the `file_paths` section of your deployment scripts.
2. Translate the **Falco** suggestions into YAML blocks inside `falco_rules.local.yaml`, ensuring you append the corresponding `mitre_defense_evasion` or `mitre_credential_access` tags.
3. Update the OpenObserve `mitre_lookup.csv` via the automated script to ensure the new `[Txxxx]` tags resolve gracefully in the SOC dashboards.
