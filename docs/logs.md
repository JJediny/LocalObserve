## LOG_SOURCES_GUIDE.md

# Log Sources Configuration Guide

This guide explains how to configure each log source and add new ones.

## Journald (Systemd Journal)

### What it captures
- All system messages from systemd-managed services
- Kernel logs
- User-space application logs
- Boot messages

### Configuration in Alloy
```yaml
loki.source.journald "logs" {
  path    = "/var/log/journal"
  matches = [
    "PRIORITY=0",  # Emergency
    "PRIORITY=1",  # Alert
    "PRIORITY=2",  # Critical
    "PRIORITY=3",  # Error
    "PRIORITY=4",  # Warning
    "PRIORITY=5",  # Notice
    "PRIORITY=6",  # Info
  ]
}
```

### Query examples in Grafana
```
# All journald logs
{job="journald"}

# Only errors and above
{job="journald", level=~"emergency|alert|critical|error"}

# Specific unit (e.g., docker)
{job="journald", unit="docker.service"}

# Specific boot
{job="journald", boot_id="abc123..."}
```

### Troubleshooting
- Ensure `/var/log/journal` is readable by the container
- Check Alloy container has `DAC_READ_SEARCH` capability
- View host journald: `journalctl -n 50`

---

## Syslog (RFC 5424)

### What it captures
- Messages from rsyslog, syslog-ng, or any RFC 5424 compatible sender
- Application logs configured to send to syslog
- Network-based syslog messages

### Configuration in Alloy
```yaml
loki.source.syslog "syslog" {
  listener {
    address             = "0.0.0.0:514"
    protocol            = "rfc5424"
    use_incoming_timestamp = true
    location            = "UTC"
  }
}
```

### Setting up rsyslog to forward logs
Edit `/etc/rsyslog.d/99-loki.conf`:
```bash
# Send all logs to syslog receiver
*.* @@127.0.0.1:514
```

Then restart rsyslog:
```bash
sudo systemctl restart rsyslog
```

### Query examples
```
# All syslog logs
{job="syslog"}

# Specific application
{job="syslog", app="nginx"}

# Specific severity
{job="syslog", severity="error"}

# Multiple apps
{job="syslog", app=~"nginx|postgres"}
```

### Troubleshooting
- Test connectivity: `echo "test message" | nc -u localhost 514`
- Check rsyslog status: `sudo systemctl status rsyslog`
- View syslog logs: `tail -f /var/log/syslog`

---

## Systemd Units

### What it captures
- Logs from systemd services
- System units, user units, and timers
- Service state changes
- Startup and shutdown messages

### Configuration in Alloy
```yaml
loki.source.systemd "systemd" {
  forward_to = [loki.write.default.receiver]
}
```

### Query examples
```
# All systemd logs
{job="systemd"}

# Specific unit
{job="systemd", unit="nginx.service"}

# User units
{job="systemd", user_unit!=""}

# Errors only
{job="systemd"} | json | level="error"
```

### View systemd logs on host
```bash
# All systemd logs
journalctl -xe

# Specific unit
journalctl -u nginx.service -n 50

# Real-time
journalctl -f
```

### Troubleshooting
- Check Alloy has access to journal: `docker-compose exec alloy journalctl -n 5`
- Verify systemd is running: `systemctl is-system-running`

---

## OSQuery

### What it captures
- System information queries
- File integrity monitoring
- Process monitoring
- Network connection logs
- Compliance checks

### Prerequisites
Install OSQuery on the host:
```bash
# Ubuntu/Debian
sudo apt-get install osquery

# macOS
brew install osquery
```

### Configuration
1. Create OSQuery config at `/etc/osquery/osquery.conf`
2. Configure results to log to `/var/log/osquery/osqueryd.results.log`
3. Ensure Alloy can read the log file

Example osquery.conf:
```json
{
  "options": {
    "config_plugin": "filesystem",
    "logger_plugin": "filesystem",
    "logger_path": "/var/log/osquery",
    "disable_logging": false,
    "schedule_splay_percent": 10
  },
  "decorators": {
    "load": [
      "SELECT uuid AS host_uuid FROM system;",
      "SELECT user AS username FROM logged_in_users ORDER BY time DESC LIMIT 1;"
    ]
  },
  "schedule": {
    "system_info": {
      "query": "SELECT * FROM system_info;",
      "interval": 3600
    },
    "process_monitoring": {
      "query": "SELECT * FROM processes WHERE state != 'S' LIMIT 100;",
      "interval": 10
    }
  }
}
```

### Query examples
```
# All OSQuery logs
{job="osquery"}

# Recent queries
{job="osquery"} | json | fields timestamp, query, action

# System info results
{job="osquery"} | json | type="result"
```

### Troubleshooting
- Check OSQuery is running: `ps aux | grep osqueryd`
- View logs: `tail -f /var/log/osquery/osqueryd.results.log`
- Test query: `osqueryi --json "SELECT * FROM system_info;"`

---

## Falco Security

### What it captures
- Suspicious system behavior
- Process execution anomalies
- Network activity violations
- Privilege escalation attempts
- Container escape attempts

### Architecture
```
Falco (running in container)
     (HTTP POST)
Falcosidekick (port 2801)
     (gRPC/HTTP)
Loki (stores in S3/MinIO)
    
Grafana (visualizes)
```

### Configuration in docker-compose
```yaml
falco:
  image: falcosecurity/falco:latest
  privileged: true
  environment:
    - FALCO_K8S_AUDIT_ENDPOINT=
    - FALCO_HOSTNAME=localhost

falcosidekick:
  image: falcosecurity/falcosidekick:latest
  environment:
    - LOKI_HOST=gateway
    - LOKI_PORT=3100
    - LOKI_TENANT=tenant1
    - LISTEN_PORT=2801
```

### Query examples
```
# All Falco alerts
{job="falco"}

# Critical alerts
{job="falco"} | json | priority="critical"

# Specific rule
{job="falco"} | json | rule="Suspicious Process"

# By container
{job="falco", container="mysql"} | json | fields timestamp, rule, container
```

### Custom Falco rules
Edit `/etc/falco/rules.d/custom-rules.yaml`:
```yaml
- rule: My Custom Rule
  desc: Description of what this detects
  condition: >
    spawned_process and container and
    proc.name in (suspicious_binary)
  output: >
    Custom alert (user=%user.name container_id=%container.id proc=%proc.cmdline)
  priority: WARNING
```

### Troubleshooting
- Check Falco: `docker-compose ps falco`
- View Falco logs: `docker-compose logs -f falco | head -50`
- Check Falcosidekick: `docker-compose logs -f falcosidekick`
- Test connectivity: `curl http://localhost:2801/health`

---

## Adding Custom Log Sources

### Pattern: File-based logs

```yaml
loki.source.file "my_app" {
  targets = [
    {
      "__path__" = "/var/log/my_app/*.log",
      "job"      = "my_app",
      "app"      = "my_app"
    }
  ]
  relabel_rules = discovery.relabel.my_app.rules
  forward_to    = [loki.write.default.receiver]
}

discovery.relabel "my_app" {
  targets = [{"__meta_myapp_source": "file"}]
  
  rule {
    target_label = "job"
    replacement  = "my_app"
  }
}
```

### Pattern: HTTP push-based logs

```yaml
loki.source.loki_push_api "my_api" {
  server {
    http_listen_address = "0.0.0.0"
    http_listen_port    = 3500
  }
  labels = {
    job = "my_api"
  }
  forward_to = [loki.write.default.receiver]
}
```

Then POST logs to: `http://localhost:3500/loki/api/v1/push`

### Pattern: Command-based logs

```yaml
loki.source.syslog "custom_cmd" {
  listener {
    address = "127.0.0.1:6514"
  }
  forward_to = [loki.write.default.receiver]
}
```

Configure your app to send syslog to `127.0.0.1:6514`

---

## Relabeling and Processing

### Add custom labels
```yaml
discovery.relabel "my_source" {
  targets = [{"__meta_source": "my_source"}]
  
  rule {
    target_label = "environment"
    replacement  = "production"
  }
  
  rule {
    target_label = "team"
    replacement  = "platform"
  }
}
```

### Extract from log content
```yaml
discovery.relabel "parse_json" {
  targets = [{"__meta_parser": "json"}]
  
  rule {
    source_labels = ["__message__"]
    regex         = ".*user=([^,]+).*"
    target_label  = "username"
  }
}
```

### Conditional relabeling
```yaml
discovery.relabel "conditional" {
  targets = [{"__meta_source": "test"}]
  
  rule {
    source_labels = ["job"]
    regex         = "error.*"
    target_label  = "severity"
    replacement   = "high"
  }
}
```

---

## References

- [Alloy Loki Sources](https://grafana.com/docs/alloy/latest/reference/components/loki.sources/)
- [Falco Documentation](https://falco.org/docs/)
- [Falcosidekick Outputs](https://github.com/falcosecurity/falcosidekick)
- [OSQuery Documentation](https://osquery.io/docs/installation/linux/)


## LOG_SOURCE_EXPANSION.md

# Log Source Expansion Plan

This document outlines additional logging and telemetry sources that would make the repository more useful for complete local Linux monitoring while preserving its low-write design goals.

## Guiding principle

New sources should be added in tiers.

The repository should avoid jumping from a minimal local setup directly to a heavyweight full-host observability footprint.

Each additional source should be evaluated for:

- signal value
- write amplification
- runtime overhead
- operational complexity
- portability across local Linux environments

## Current validated sources

- osquery results file
- Falco alerts through Falcosidekick
- optional OTLP logs through the OpenTelemetry Collector comparison profile

## Recommended expansion tiers

### Tier 1: High-value host logs with low complexity

These are the best next additions for broader host visibility.

#### 1. Journald

Recommended focus:

- `sudo`
- `sshd`
- `systemd`
- `kernel`
- `polkit`
- `NetworkManager`

Why it helps:

- broad visibility without adding many new host agents
- useful for auth, service failure, package, and kernel signal
- typically a better source of truth than scraping many separate text logs on modern Linux systems

Tradeoff:

- depends on host journald layout and Docker bind mount behavior

#### 2. Authentication logs

Potential sources:

- journald auth-related units and facilities
- `/var/log/auth.log` on Debian/Ubuntu-style systems

Why it helps:

- login attempts
- privilege escalation attempts
- PAM-related failures
- SSH activity

Tradeoff:

- can duplicate journald if both are enabled without care

#### 3. Kernel log stream

Potential sources:

- journald kernel messages
- `dmesg` snapshots for troubleshooting

Why it helps:

- visibility into OOMs, crashes, driver issues, and certain exploit side effects

Tradeoff:

- high-volume kernels may need filtering

### Tier 2: System security and change visibility

#### 4. Package manager logs

Potential sources:

- `apt`
- `dpkg`
- `dnf`
- `rpm`

Why it helps:

- unexpected installs or upgrades
- persistence through package operations
- forensic reconstruction of system changes

#### 5. Firewall and network policy logs

Potential sources:

- `nftables`
- `iptables`
- `ufw`

Why it helps:

- local network policy changes
- suspicious allowed or denied traffic
- host exposure drift

#### 6. Resolver and DNS logs

Potential sources:

- `systemd-resolved`
- `dnsmasq`
- `unbound`

Why it helps:

- DNS resolution behavior
- suspicious or failed lookups
- troubleshooting outbound issues

### Tier 3: Container and runtime visibility

#### 7. Docker events

Potential sources:

- Docker event stream
- daemon logs
- selected container stdout/stderr

Why it helps:

- container lifecycle visibility
- rapid forensic inspection during ad hoc analysis
- stronger context around Falco container events

Tradeoff:

- can increase event volume significantly if collected too broadly

#### 8. Docker metadata snapshots

Potential sources:

- periodic inspect-style snapshots
- image label and network metadata

Why it helps:

- context for containers that no longer exist by the time an incident is reviewed

### Tier 4: Advanced and optional telemetry

#### 9. auditd or audit subsystem logs

Why it helps:

- high-fidelity security event coverage
- stronger file, process, and privilege signal than periodic polling alone

Tradeoff:

- can materially increase host write load
- requires careful tuning to stay aligned with this repository's design goals

#### 10. SMART and disk health telemetry

Potential sources:

- periodic `smartctl` snapshots
- NVMe SMART data

Why it helps:

- better host health visibility
- useful for laptop, workstation, and lab hardware monitoring

#### 11. eBPF-heavy process or network sources

Potential sources:

- opt-in eBPF event streams
- higher fidelity process/network telemetry

Why it helps:

- stronger live detection and timeline reconstruction

Tradeoff:

- this is the easiest place to violate the repository's lightweight design goals
- should remain strictly optional

## Recommended implementation order

1. journald
2. auth logs
3. kernel logs
4. package manager logs
5. firewall logs
6. resolver logs
7. Docker events and selected container logs
8. auditd-style event sources only if the write budget remains acceptable

## Recommendation for open-source positioning

When published, the repository should describe these as staged expansions rather than promising complete system monitoring out of the box.

A good message is:

- the default profile is intentionally small
- broader host visibility is possible
- each added source should be justified against the repository's low-write operating model


## HOST_LOG_IMPORTS.md

# Host Log Imports

This repository is optimized for low-noise continuous monitoring, so it should not tail all of `/var/log` all the time.

A more efficient pattern is:

1. keep the default always-on stack small
2. stage selected legacy or investigative logs into `./.data/host-import/inbox/`
3. let Alloy ingest those staged files under `job="host_import"`
4. use parser-aware subdirectories so Alloy can recover source timestamps where practical

## Why this is the efficient option

Your host has a mix of:

- high-value security logs
- rotating troubleshooting logs
- one-off installer logs
- binary login databases that should not be shipped raw

If you continuously ingest all of them, you pay for a lot of low-value churn.

Staging logs on demand gives you:

- deliberate ingestion instead of accidental full-host scraping
- preserved low-write defaults for daily monitoring
- easy historical imports of rotated logs like `auth.log.1` or `kern.log.1`
- unique batch directories so the same source can be imported more than once when needed
- a simple path for investigation batches without changing the main stack profile

## Recommended source classes

### Good candidates for regular on-demand import

- `auth.log`, `auth.log.1`
- `kern.log`, `kern.log.1`
- `dpkg.log`, `dpkg.log.1`
- `apt/history.log`, `apt/term.log`
- `audit/audit.log`
- `suricata/*.json`
- `crowdsec-firewall-bouncer.log`
- `openvpn/*`

### Good candidates for occasional troubleshooting import

- `boot.log*`
- `dmesg*`
- `Xorg.*`
- `lightdm/*`
- `gpu-manager*.log`
- `installer/*`
- `cups/*`

### Do not ingest raw by default

These are binary or better handled through purpose-built commands:

- `wtmp`
- `btmp`
- `lastlog`
- `faillog`

Use `last`, `lastb`, and account-focused tooling instead of raw text shipping for those.

## Commands

List the built-in staging profiles:

- `./stage-host-logs.sh profiles`

Stage a curated group:

- `./stage-host-logs.sh stage-profile security`
- `./stage-host-logs.sh stage-profile packages`
- `./stage-host-logs.sh stage-profile desktop`

Stage specific files directly:

- `./stage-host-logs.sh stage-files /var/log/auth.log.1 /var/log/kern.log.1`
- `sudo ./stage-host-logs.sh stage-files /var/log/audit/audit.log /var/log/suricata/eve.json`
- `./stage-host-logs.sh stage-files /var/log/auth.log.2.gz /var/log/dpkg.log.1`

See staged batches:

- `./stage-host-logs.sh status`

Clear old staged imports:

- `./stage-host-logs.sh clean`

## Querying imported logs

Imported files are sent to Loki with:

- `job="host_import"`
- `ingest_mode="ondemand"`
- `host_import_format="syslog" | "dpkg" | "json" | "plain"`

Useful starting queries in Grafana:

- `{job="host_import"}`
- `{job="host_import", filename=~".*auth.*"}`
- `{job="host_import", filename=~".*kern.*"}`
- `{job="host_import", filename=~".*suricata.*"}`

## Timestamp behavior

The on-demand import path now applies parser-aware timestamp recovery for the most useful legacy formats:

- `syslog` batches try to parse classic timestamps like `May 13 14:22:01`
- `dpkg` batches parse timestamps like `2026-05-13 14:22:01`
- `json` batches try common `timestamp` and `time` RFC3339-style fields
- `plain` batches still use Loki ingestion-time timestamps

The original timestamps are still preserved in the log line content.

This means authentication, kernel, and package-manager imports now have a better reconstructed timeline out of the box, while miscellaneous plain-text troubleshooting logs remain simple and low-overhead.

## Practical recommendation for your current `/var/log`

Given the paths on your host, the best first-pass profiles are:

- `security` for `auth.log`, `audit`, `suricata`, `crowdsec`, and `openvpn`
- `packages` for `apt`, `dpkg`, and `alternatives`
- `kernel` for `kern.log`, `boot.log`, and `dmesg`

That gives you a high-signal investigative path without continuously ingesting desktop, installer, printing, or binary login database noise.

## Parser-aware staging layout

The staging helper now sorts copied files into one of these subdirectories inside each batch:

- `syslog/`
- `dpkg/`
- `json/`
- `plain/`

That layout is what lets Alloy apply more accurate timestamp parsing for common legacy formats while still keeping the workflow simple.
