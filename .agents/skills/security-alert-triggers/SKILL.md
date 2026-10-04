---
name: security-alert-triggers
description: Safe, innocent trigger commands and automated runner for security alerts across Falco, OSquery, ClamAV, RSigma, and AI Agent observability in LocalObserve.
tags:
  - security
  - alerts
  - falco
  - osquery
  - clamav
  - rsigma
  - agent-observability
  - openobserve
  - mitre-attack
  - desktop-notifications
---

# Security Alert Triggers Skill

This skill provides a curated catalog of **innocent, non-destructive commands** to safely trigger, validate, and exercise all configured detection alerts across the LocalObserve monitoring stack without compromising host security or causing operational disruption.

---

## 1. Quick Start

Run the automated trigger runner to exercise all alert pipelines and dispatch native desktop notifications:

```bash
# Trigger all alert streams and dispatch native Linux desktop notifications via notify-send
python3 tools/trigger_alerts.py --all

# Or trigger an individual stream
python3 tools/trigger_alerts.py --stream falco
python3 tools/trigger_alerts.py --stream osquery
python3 tools/trigger_alerts.py --stream clamav
python3 tools/trigger_alerts.py --stream agent
python3 tools/trigger_alerts.py --stream rsigma
python3 tools/trigger_alerts.py --stream system-logs

# Replay any queued alerts to your desktop screen without re-triggering
python3 tools/trigger_alerts.py --notify

# Verify OpenObserve stream counts and alert dispatches only
python3 tools/trigger_alerts.py --verify
```

---

## 2. Desktop Notification Integration (`notify-send`)

### Why the Host Notifier Bridge Is Required
Docker containers execute in an isolated namespace and do not have access to the user's host DBus session bus (`/run/user/1000/bus`) or Wayland/X11 display server. To bridge containerized alerts into native host desktop notifications:
1. The containerized `alert-receiver` writes alert JSON artifacts to `/var/log/alerts/` (bind-mounted to host `.data/alerts/`).
2. The host-side notifier ([`tools/desktop_notifier.py`](file:///home/john/LocalObserve/tools/desktop_notifier.py)) reads `.data/alerts/` and fires native `notify-send` popups with urgency styling, icons, and audio cues.

### Useful Taskfile Commands for Desktop Alerting
```bash
# Replay all pending/queued alerts to screen once
task notify-desktop-replay

# Run the persistent background daemon watching for new alerts in real time
task notify-desktop

# Dismiss/clear stuck notification popups from screen
task notify-desktop-dismiss
```

---

## 3. Innocent Command Reference Matrix

| Stream / Engine | Alert Rule Name | MITRE ATT&CK | Safe Innocent Trigger Command | Why It Is Safe & Innocent | Expected Log / Match Field |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Falco** | `Falco-High-Severity` / `Read sensitive file untrusted` | T1555 (Credentials) | `python3 -c "open('/etc/security/pwquality.conf').read(10)"` | Read-only check of benign world-readable password quality configuration. No credentials exposed or modified. | `rule: "Read sensitive file untrusted"`, `priority: "Warning"` |
| **Falco** | `Falco-Shadow-Read` | T1003.008 (/etc/shadow) | `python3 -c "try: open('/etc/shadow')\nexcept Exception: pass"` | Unprivileged, non-root process triggers `openat` syscall on shadow path; fails safely with permission denied. | `rule: "Shadow File Read by Non-Auth Process"` or `rule: "Read sensitive file untrusted"` |
| **Falco** | `LD-PRELOAD-Injection` | T1574.006 (Hijack Execution) | `LD_PRELOAD=/lib/x86_64-linux-gnu/libc.so.6 id` | Preloads standard system GNU C library (already linked by the process). Executes standard benign `id`. | `rule: "Hijack Execution Flow with LD_PRELOAD"`, env contains `LD_PRELOAD=` |
| **Falco** | `Falco-Tmp-Execution` | T1059 (Execution) | `cp /bin/true /tmp/innocent_test_bin && /tmp/innocent_test_bin && rm /tmp/innocent_test_bin` | Copies GNU `true` (which immediately returns exit code 0) to `/tmp`, executes it, and removes it immediately. | `rule: "Execution from Temporary Directory"` |
| **OSquery** | `OSquery-FIM-Critical-File-Modified` | T1546.004 (Persistence) | `touch ~/.bashrc` | Updates the modification timestamp on existing benign user profile without modifying file contents. | `name: "file_events"`, `action: "UPDATED"` |
| **OSquery** | `OSquery-New-Cron-Job` | T1053.003 (Cron Persistence) | `(crontab -l 2>/dev/null; echo "# benign test: curl -s http://localhost:5080/healthz > /dev/null") \| crontab -` | Benign commented crontab entry referencing localhost health endpoint; cleans up via `crontab -r`. | `name: "crontab"`, `command LIKE '%curl%'` |
| **OSquery** | `OSquery-SUID-Binary-Added` | T1548.001 (SUID Abuse) | `docker exec localobserve-osquery-1 osqueryi --json "SELECT * FROM suid_bin LIMIT 5"` | Queries existing system SUID binaries via the container daemon without elevating permissions. | `name: "suid_bin_changes"` |
| **ClamAV** | `ClamAV-Malware-FOUND` | N/A (Standard AV Test) | `echo "/tmp/innocent_eicar_test.com: FOUND Win.Test.EICAR_HDB-1" >> .data/clamav/scan.log` | Uses the official EICAR antivirus test signature string designed specifically for safe AV alert testing. | `stream: "clamav"`, `scan_status: "FOUND"` |
| **AI Agent** | `AIAgent-Sensitive-File-Access` | T1003, T1565.001 | `uv run python tools/agent_session_demo.py --quick` | Scripted synthetic agent emits OTLP log telemetry requesting `/etc/shadow` tool call without altering the file. | `stream: "agent_logs"`, `gen_ai_tool_args LIKE '%/etc/shadow%'` |
| **AI Agent** | `AIAgent-Tool-Error-Spike` | T1059 (Execution Probe) | `uv run python tools/agent_session_demo.py --quick` | Emits a synthetic tool call error (`otel_status_code = "ERROR"`) simulating a failed connection. | `stream: "agent_logs"`, `otel_status_code = 'ERROR'` |
| **RSigma** | `Suspicious Namespace Unshare` | T1059, T1071 | `curl -s -X POST http://localhost:9090/api/v1/events -H "Content-Type: application/json" -d '{"name": "unshare", "cmdline": "unshare --user --map-root-user /bin/bash", "pid": 99001}'` | Direct HTTP event ingestion to RSigma streaming evaluator. No actual namespace unshare command is executed on the host. | RSigma webhook fires alert to `alert-receiver:9000` |
| **RSigma** | `AI Agent Dangerous Shell` | T1059, T1561.002 | `curl -s -X POST http://localhost:9090/api/v1/events -H "Content-Type: application/json" -d '{"service_namespace": "agent", "gen_ai_tool_name": "run_shell", "gen_ai_tool_args": "rm -rf /", "pid": 99002}'` | Harmless synthetic event posted to RSigma; tests detection of destructive commands without running any shell. | RSigma webhook fires `AI Agent Dangerous Shell Command` |
| **SystemLogs** | `SystemLogs-Auth-Failure-Spike` | T1110 (Brute Force) | `curl -s -u root@example.com:Complexpass#123 -X POST "http://localhost:5080/api/default/system_logs/_json" -d '[{"message": "sshd: Failed password for invalid user admin from 192.168.1.100 port 22"}]'` | Benign simulated authentication failure message ingested directly to OpenObserve log stream. | `stream: "system_logs"`, `message LIKE '%Failed password%'` |
| **SystemLogs** | `SystemLogs-Sudo-Abuse` | T1548.003 (Sudo Abuse) | `curl -s -u root@example.com:Complexpass#123 -X POST "http://localhost:5080/api/default/system_logs/_json" -d '[{"message": "sudo: guest : TTY=pts/1 ; PWD=/tmp ; USER=root ; COMMAND=/bin/sh"}]'` | Benign simulated sudo log entry for non-standard user ingested to OpenObserve log stream. | `stream: "system_logs"`, `message LIKE '%COMMAND=%'` |

---

## 4. Verification Queries

### OpenObserve SQL Queries

Check hits across each stream via OpenObserve API:

```bash
# 1. Falco Hits:
curl -u root@example.com:Complexpass#123 -X POST "http://localhost:5080/api/default/_search" \
  -H "Content-Type: application/json" \
  -d '{"query": {"sql": "SELECT rule, priority, output FROM \"falco\" ORDER BY _timestamp DESC LIMIT 5"}}'

# 2. ClamAV Malware Hits:
curl -u root@example.com:Complexpass#123 -X POST "http://localhost:5080/api/default/_search" \
  -H "Content-Type: application/json" \
  -d '{"query": {"sql": "SELECT scan_path, scan_status, virus_name FROM \"clamav\" WHERE scan_status = '\''FOUND'\'' LIMIT 5"}}'

# 3. AI Agent Sensitive File Access:
curl -u root@example.com:Complexpass#123 -X POST "http://localhost:5080/api/default/_search" \
  -H "Content-Type: application/json" \
  -d '{"query": {"sql": "SELECT gen_ai_tool_name, gen_ai_tool_args, otel_status_code FROM \"agent_logs\" LIMIT 5"}}'

# 4. OSquery Events:
curl -u root@example.com:Complexpass#123 -X POST "http://localhost:5080/api/default/_search" \
  -H "Content-Type: application/json" \
  -d '{"query": {"sql": "SELECT name, action FROM \"osquery\" ORDER BY _timestamp DESC LIMIT 5"}}'
```

### Webhook Alert Receiver Verification

Inspect dispatched alert JSON files received by `alert-receiver`:

```bash
docker exec localobserve-alert-receiver-1 ls -la /var/log/alerts
# View the newest alert:
docker exec localobserve-alert-receiver-1 sh -c 'cat /var/log/alerts/$(ls -t /var/log/alerts | head -1)'
```

---

## 5. Related Documentation

- [Developing Realtime Indicators of Compromise (IoC) Alerts Guide](file:///home/john/LocalObserve/docs/developing_realtime_ioc_alerts.md)
- [Alert Payload Schema & Action Playbook Specification](file:///home/john/LocalObserve/docs/alerting_payload_schema.md)
- [Multi-Runtime & Alerting Deployment Guide](file:///home/john/LocalObserve/docs/runtimes_alerting_and_resource_guide.md)
