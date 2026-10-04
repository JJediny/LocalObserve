# Developing Alerts for Suspicious Real-Time Indicators of Compromise (IoCs)

This guide documents the architecture, rule-authoring methodology, testing workflows, and best practices for developing real-time detection alerts across the LocalObserve security stack. It covers kernel-level syscall interception (**Falco**), host state and file integrity monitoring (**OSquery**), streaming Sigma rule matching (**RSigma**), malware and signature detection (**ClamAV**), AI Agent behavioral telemetry (**AI Agent Observability**), and log correlation analytics (**OpenObserve**).

---

## 1. Real-Time Detection Architecture

LocalObserve implements a multi-layer defense-in-depth detection pipeline designed to intercept Indicators of Compromise (IoCs) at varying abstraction layers with minimal latency and negligible host overhead.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   TELEMETRY SOURCES                                         │
│                                                                                             │
│  ┌───────────────────────┐   ┌──────────────────────┐   ┌────────────────────────────────┐  │
│  │     Kernel Syscalls   │   │  Host State & FIM    │   │      AI Agent Telemetry        │  │
│  │   (modern-eBPF probe) │   │  (Inotify / Tables)  │   │     (OTLP Log Instrumentation) │  │
│  │        [Falco]        │   │      [OSquery]       │   │        [agent-demo / SDK]      │  │
│  └───────────┬───────────┘   └──────────┬───────────┘   └───────────────┬────────────────┘  │
└──────────────┼──────────────────────────┼───────────────────────────────┼───────────────────┘
               │ JSONL                    │ JSON Results                  │ OTLP HTTP (:4318)
               ▼                          ▼                               ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                          OPENTELEMETRY COLLECTOR CONTRIB                                    │
│                                                                                             │
│  • file_log receivers (tailing /var/log/{falco,osquery,clamav})                             │
│  • Memory limiter & Batch processors                                                        │
│  • OTTL source-level volume reduction (filter/drop_osquery_inventory)                       │
│  • Schema flattening & field normalization (transform/flatten)                              │
└──────────────────────────────┬───────────────────────────────┬──────────────────────────────┘
                               │                               │
                               ▼                               ▼
┌──────────────────────────────────────────────┐ ┌────────────────────────────────────────────┐
│      STREAMING EVALUATION (SUB-SECOND)       │ │     LOG AGGREGATION & SQL ANALYTICS        │
│                                              │ │                                            │
│            rsigma Engine (:9090)             │ │          OpenObserve Engine (:5080)        │
│  • In-memory Sigma YAML evaluation           │ │  • Stream partitioning (falco, osquery,    │
│  • Zero-disk evaluation of streaming events  │ │    agent_logs, clamav, system_logs)        │
│  • Immediate webhook emission upon match     │ │  • Real-time & Scheduled SQL alert checks  │
│                                              │ │  • Threshold & sliding time window queries │
└──────────────────────┬───────────────────────┘ └─────────────────────┬──────────────────────┘
                       │                                               │
                       │ Webhook JSON Payload                          │ Webhook JSON Payload
                       ▼                                               ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                              ALERT RECEIVER & DISPATCH (:9000)                              │
│                                                                                             │
│  • Destination: http://alert-receiver:9000/hooks/security-alert-open                        │
│  • Handler script: /hooks/notify.sh                                                         │
│  • Persistent alert artifact storage: /var/log/alerts/<alert_id>.json                       │
│  • Desktop visual alert: notify-send --urgency=critical                                     │
│  • Integrations: Slack, Email, Generic SIEM Webhook, Automated Action Playbooks             │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Detection Layer Comparison Matrix

| Detection Engine | Layer / Focus | Telemetry Source | Typical Detection Latency | Best Suited For IoCs |
| :--- | :--- | :--- | :--- | :--- |
| **Falco (eBPF)** | Kernel / System Calls | Linux Kernel tracepoints (`sys_enter`, `sys_exit`) via `modern_ebpf` | `< 100 ms` | Dynamic linker hijacking (`LD_PRELOAD`), unprivileged `/etc/shadow` reads, interactive container shells, `/dev/shm` or `/tmp` code execution. |
| **RSigma** | Streaming Log Evaluation | HTTP `/api/v1/events` or OTel collector forwarder | `< 250 ms` | Fast matching of standardized Sigma rules over command lines, namespace unshares, process arguments, and AI agent tool requests. |
| **OSquery** | Host State & FIM | Kernel inotify + Linux audit / periodic SQL sweeps | Real-time for FIM; `1m–15m` for sweeps | File modification to monitored configs (`.bashrc`, SSH keys), persistence via crontab / systemd, SUID binary additions, user creation. |
| **OpenObserve Alerts** | Log Correlation & Aggregation | Indexed log streams (`falco`, `osquery`, `agent_logs`, `clamav`, `system_logs`) | `1m–15m` (configurable) | Threshold spikes (e.g. $\ge 5$ tool call errors in 5 min), cross-stream joins, aggregate brute-force detection, pipeline health baselines. |
| **ClamAV** | Antivirus & File Signatures | Filesystem scanner / clamd socket | On-scan completion | Malicious payload drops, webshell signatures, EICAR test verification, known malware hashes. |

---

## 3. Developing Falco eBPF Rules

Falco inspects system calls directly at the kernel boundary using the modern eBPF driver. Rules are written in YAML and loaded from `falco_rules.local.yaml` (container sidecar) and `/etc/falco/rules.d/` (host service).

### Rule Anatomy

```yaml
- rule: Hijack Execution Flow with LD_PRELOAD
  desc: Detect LD_PRELOAD in process environment for dynamic linker hijacking.
  condition: >
    spawned_process
    and proc.env contains "LD_PRELOAD="
  output: >
    Process executed with LD_PRELOAD environment variable |
    user=%user.name command=%proc.cmdline env=%proc.env container=%container.id
  priority: WARNING
  tags: [mitre_privilege_escalation, mitre_defense_evasion, T1574.006]
```

### Key Fields & Conventions

1. **`rule`**: Unique, descriptive rule title.
2. **`condition`**: Logical expression evaluating Falco filter fields:
   - `spawned_process`: Shorthand macro for `evt.type = execve and evt.dir = <`.
   - `open_read`: Syscalls opening files for reading (`evt.type in (open, openat, openat2) and evt.is_open_read = true`).
   - `proc.cmdline` / `proc.exepath`: Process command string and binary path.
   - `proc.env`: Environment variables array.
   - `container.id`: `host` for bare-metal processes; container hash for Docker/Podman workloads.
3. **`output`**: Human- and parser-readable template string using `%field.name` tokens.
4. **`priority`**: Severity ranking: `NOTICE`, `WARNING`, `CRITICAL`, `ALERT`, or `EMERGENCY`.
   > [!IMPORTANT]
   > Ensure the priority aligns with OpenObserve's `Falco-High-Severity` alert query, which monitors `priority IN ('Notice','Warning','Critical','Alert','Emergency')`.
5. **`tags`**: MITRE ATT&CK technique IDs (`T1574.006`), tactics (`mitre_defense_evasion`), and environmental scopes (`host`, `container`).

### Best Practices for Falco Rules

- **Use built-in macros**: Leverage macros like `sensitive_files`, `user_known_container_binaries`, and `shell_procs` to keep conditions concise.
- **Differentiate host vs container**: To prevent alert fatigue in build containers, scope host-only attacks with `container.id = host`.
- **Minimize expensive string searches**: Place fast checks (`evt.type = execve`) before substring scans (`proc.cmdline contains "..."`).

---

## 4. Developing Sigma Rules for RSigma

RSigma executes Sigma detection logic over streaming JSON events in memory without maintaining heavy database indexes. Rules reside in `rules/sigma/active_rules/*.yaml`.

### Rule Anatomy

```yaml
title: Suspicious Namespace Unshare Command
id: 718c5dbc-b1a3-419b-a329-e7721d294257
status: experimental
description: Detects unshare command executed with --user flag, commonly used for container escapes or privilege escalation.
references:
  - https://man7.org/linux/man-pages/man1/unshare.1.html
author: LocalObserve Team
date: 2026-07-26
logsource:
  category: process_creation
  product: linux
detection:
  selection:
    name: unshare
    cmdline|contains:
      - '--user'
      - '-U'
  filter:
    cmdline|contains:
      - '--mount'
  condition: selection and not filter
level: high
tags:
  - attack.t1059
  - attack.t1071
  - attack.privilege_escalation
```

### Developing AI Agent Sigma Detections

RSigma also processes AI Agent tool telemetry forwarded from `agent_logs`:

```yaml
title: AI Agent Dangerous Shell Command
id: 5a1e0000-0000-4a91-a1a1-000000000001
status: stable
description: Detects high-risk destructive shell commands initiated by an AI agent tool call.
logsource:
  category: ai_agent
  product: localobserve
detection:
  selection:
    gen_ai_tool_name: run_shell
    gen_ai_tool_args|contains:
      - 'rm -rf /'
      - 'mkfs.'
      - 'dd if=/dev/'
      - ':(){ :|:& };:'
  condition: selection
level: critical
tags:
  - attack.t1059
  - attack.t1561.002
```

### Field Transformation Rules

When authoring Sigma rules for RSigma:
- The `logsource` identifies the pipeline schema.
- Condition modifiers like `|contains`, `|startswith`, and `|endswith` are evaluated directly against the incoming JSON keys.
- Matches instantly dispatch an HTTP POST request to `http://alert-receiver:9000/hooks/security-alert-open` containing rule details, MITRE tags, and the triggering payload.

---

## 5. Developing OSquery Real-Time & Scheduled Queries

OSquery exposes the underlying operating system as a relational SQLite database. Detection logic is defined in `osqueryd.conf`.

### Event-Driven Tables (FIM) vs Scheduled Sweeps

OSquery supports two detection paradigms:

1. **Event-Based Tables (`file_events`, `process_events`)**:
   Powered by inotify and the Linux audit subsystem. Changes are recorded continuously in real time.
   ```json
   "file_events": {
     "query": "SELECT * FROM file_events;",
     "interval": 300,
     "description": "FIM events for profile and init scripts [T1546.004] [T1037.004] [T1070.003]",
     "removed": false
   }
   ```
   Monitored file paths are configured under the `file_paths` section:
   ```json
   "file_paths": {
     "bash_profiles": [
       "/home/%/.bashrc",
       "/root/.bashrc",
       "/etc/profile.d/%%"
     ],
     "ssh_keys": [
       "/home/%/.ssh/%%",
       "/root/.ssh/%%"
     ]
   }
   ```

2. **Differential Scheduled Queries (`crontab`, `suid_bin`, `systemd_units`)**:
   OSquery periodically runs SQL queries and logs only added or removed records (`"action": "added"`):
   ```json
   "crontab": {
     "query": "SELECT * FROM crontab;",
     "interval": 900,
     "description": "Scheduled cron jobs - detect persistence via cron [T1053.003]"
   }
   ```

### Tuning for System Performance and SSD Protection

High-frequency inventory sweeps can cause excessive disk I/O and SSD wear:
- **Low-churn persistence tables** (`crontab`, `startup_items`, `systemd_units`): Poll every `300s` to `900s`.
- **High-churn inventory tables** (`listening_ports`, `processes`, `mounts`): Dropped at the OpenTelemetry Collector boundary via `filter/drop_osquery_inventory` unless explicitly needed for deep forensics.

---

## 6. Developing OpenObserve Stream Alerts

OpenObserve evaluates alerting conditions over incoming log streams using SQL queries. All alert configurations are version-controlled in `alerts/openobserve/alerts.json` and synchronized via `tools/oo-alerts.sh`.

### Alert Object Schema

```json
{
  "name": "Falco-Shadow-Read",
  "stream_type": "logs",
  "stream_name": "falco",
  "is_real_time": false,
  "query_condition": {
    "conditions": null,
    "sql": "SELECT * FROM \"falco\" WHERE rule = 'Shadow File Read by Non-Auth Process'",
    "promql": "",
    "type": "custom",
    "aggregation": null
  },
  "trigger_condition": {
    "period": 1,
    "operator": ">=",
    "frequency": 1,
    "threshold": 1,
    "silence": 10,
    "frequency_type": "minutes",
    "timezone": "UTC"
  },
  "destinations": [
    "localhost-webhook"
  ],
  "enabled": true,
  "description": "Unauthorized access attempt to /etc/shadow [T1003.008]"
}
```

### Critical Stream Naming Rule

> [!WARNING]
> OpenObserve automatically sanitizes hyphens (`-`) in stream headers to underscores (`_`).
> - An OTLP stream header `stream-name: agent-logs` creates the table `"agent_logs"`.
> - An OTLP stream header `stream-name: system-logs` creates the table `"system_logs"`.
> 
> Always quote sanitized table names in your alert SQL queries (e.g. `SELECT * FROM "agent_logs"` or `SELECT * FROM "system_logs"`).

### GitOps Synchronization

Synchronize alert definitions between the repository and a running OpenObserve cluster:

```bash
# 1. Register the alert-receiver webhook destination in OpenObserve
bash tools/oo-alerts.sh setup-destination

# 2. Import all alert definitions from alerts/openobserve/alerts.json
bash tools/oo-alerts.sh import

# 3. Export active alerts from OpenObserve back to Git
bash tools/oo-alerts.sh export

# 4. Dispatch a test webhook to verify end-to-end receipt
bash tools/oo-alerts.sh test
```

---

## 7. Developing AI Agent Observability Alerts

AI Agent tools that execute code, browse the filesystem, or interact with external APIs represent a unique threat surface. LocalObserve captures every agent tool call via OpenTelemetry structured logs.

### Instrumenting Agent Tool Telemetry

Using [`tools/agent_otel_prelude.py`](../tools/agent_otel_prelude.py):

```python
import agent_otel_prelude as prelude

# Emit tool call telemetry
prelude.emit_tool_call(
    tool_name="read_file",
    tool_args="/etc/shadow",
    ok=True,
    error=None
)
```

The resulting OTLP log record contains:
- `gen_ai_tool_name`: Name of the invoked tool (e.g. `read_file`, `run_shell`).
- `gen_ai_tool_args`: Formatted arguments passed to the tool.
- `ai_session_id`: Unique identifier correlating multi-step tool calls.
- `otel_status_code`: `OK` or `ERROR`.

### Target Alert Patterns for AI Agents

1. **Sensitive File Probing (`AIAgent-Sensitive-File-Access`)**:
   ```sql
   SELECT * FROM "agent_logs"
   WHERE (
     gen_ai_tool_args LIKE '%/etc/shadow%' OR
     gen_ai_tool_args LIKE '%/etc/sudoers%' OR
     gen_ai_tool_args LIKE '%/etc/ssh/sshd_config%' OR
     gen_ai_tool_args LIKE '%authorized_keys%' OR
     gen_ai_tool_args LIKE '%/etc/ld.so.preload%'
   )
   ```
2. **Tool Failure Spike (`AIAgent-Tool-Error-Spike`)**:
   Detects prompt-injection scanning or broken integrations:
   ```sql
   SELECT count(*) as error_count FROM "agent_logs" WHERE otel_status_code = 'ERROR'
   ```
   Trigger condition: $\ge 5$ errors within a 5-minute sliding window.

---

## 8. The Innocent Trigger Testing Workflow

Every new detection alert must be accompanied by an **innocent validation trigger** — a safe, non-destructive command that exercises the exact detection rule without altering system state, escalating privileges, or running malware.

### Step-by-Step Validation Lifecycle

```
┌─────────────────────────────────┐
│ 1. Threat Modeling & MITRE Map │ -> Identify attack technique and required log stream
└────────────────┬────────────────┘
                 ▼
┌─────────────────────────────────┐
│ 2. Author Detection Rule        │ -> Create Falco / Sigma / OSquery / OpenObserve rule
└────────────────┬────────────────┘
                 ▼
┌─────────────────────────────────┐
│ 3. Craft Innocent Trigger       │ -> Formulate benign, non-destructive test command
└────────────────┬────────────────┘
                 ▼
┌─────────────────────────────────┐
│ 4. Execute & Verify Pipelines   │ -> Run via tools/trigger_alerts.py and check hits
└────────────────┬────────────────┘
                 ▼
┌─────────────────────────────────┐
│ 5. Curate into Skill & Tests    │ -> Update security-alert-triggers skill & pytest
└─────────────────────────────────┘
```

### Adding New Triggers to `tools/trigger_alerts.py`

When authoring a new trigger, add the function to [`tools/trigger_alerts.py`](../tools/trigger_alerts.py):

```python
def trigger_custom_ioc() -> bool:
    """Safe, non-destructive validation for new IoC detection."""
    print("[+] Triggering Custom IoC Alert...")
    # Safe, read-only or harmless execution:
    try:
        subprocess.run(["stat", "/etc/hosts"], check=True)
        return True
    except Exception as e:
        print(f"[-] Trigger failed: {e}")
        return False
```

Then verify execution across all streams:

```bash
python3 tools/trigger_alerts.py --all
```

---

## 9. Tuning, Suppression & False-Positive Management

To maintain high signal-to-noise ratios, apply tuning at the earliest possible stage in the processing pipeline:

1. **Kernel Stage (Falco Exceptions)**:
   Add authorized process exceptions directly to rule conditions:
   ```yaml
   and not proc.name in (my_authorized_backup_daemon, logrotate)
   ```
2. **Collector Stage (OTTL Processors)**:
   Drop unneeded high-volume telemetry before network export using OTTL conditions in `otel-collector-config.yaml`.
3. **Analytics Stage (OpenObserve SQL)**:
   Filter expected maintenance commands or known user IDs:
   ```sql
   WHERE message LIKE '%sudo:%' AND message NOT LIKE '%authorized_admin%'
   ```
4. **Alert Receiver Stage (Action Playbooks)**:
   Configure silence periods (`"silence": 30`) in `alerts.json` to prevent notification storms when an alert fires repeatedly within a short window.

---

## 10. Related References & Runbooks

- [Alert Payload Schema & Action Playbook Specification](./alerting_payload_schema.md)
- [Security Alert Triggers Agent Skill](file:///home/john/LocalObserve/.agents/skills/security-alert-triggers/SKILL.md)
- [OpenObserve VRL & Log Enrichment Guide](./openobserve_vrl_enrichment.md)
- [Multi-Runtime & Alerting Deployment Guide](./runtimes_alerting_and_resource_guide.md)
- [MITRE ATT&CK Linux Coverage Gaps & Mapping](./mitre_linux_coverage_gaps.md)
- [Detection Rule Review & Audit](./detection_rule_review.md)
