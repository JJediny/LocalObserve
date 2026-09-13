# LocalObserve Security Alert Payload Schema & Action Playbook Specification

This specification documents the standardized JSON alert payload format used across LocalObserve, details custom `x-` vendor extensions, provides a comprehensive feature test example, and links alerting triggers to automated GitHub Actions playbooks, external Libre projects, and open pull requests.

---

## 1. Alert Payload Architecture & JSON Schema

LocalObserve alert payloads are validated against the formal JSON Schema at [`schemas/alert_payload_schema.json`](../schemas/alert_payload_schema.json).

```
┌──────────────────┐    OTTL / Webhook     ┌────────────────────────┐
│  Falco / osquery │ ────────────────────> │  rsigma Engine         │
└──────────────────┘                       └───────────┬────────────┘
                                                       │ JSON Payload + x- Extensions
                                                       ▼
┌──────────────────┐    Native Desktop     ┌────────────────────────┐
│  Desktop Notifier│ <──────────────────── │  alert-receiver        │
│  (/usr/bin/notify│                       │  (/var/log/alerts/)    │
└──────────────────┘                       └───────────┬────────────┘
                                                       │ Action Playbook Trigger
                                                       ▼
                                           ┌────────────────────────┐
                                           │  GitHub Actions / Task │
                                           │  Remediation Workflow  │
                                           └────────────────────────┘
```

### Extended `x-` Vendor Extensions

| Field Name | Type | Enum / Example | Description |
| :--- | :---: | :--- | :--- |
| `x-localobserve-source-component` | `string` | `falco-ebpf`, `osquery-daemon`, `rsigma-detector`, `otelcol-processor`, `custom-webhook` | Originating microservice telemetry source. |
| `x-localobserve-mitre-tactic` | `string` | `TA0004-privilege-escalation`, `TA0005-defense-evasion` | Mapped MITRE ATT&CK Tactic identifier. |
| `x-localobserve-mitre-technique` | `string` | `T1068`, `T1059.004`, `T1574.006` | Mapped MITRE ATT&CK Technique ID. |
| `x-localobserve-action-playbook` | `string` | `desktop-notify`, `isolate-container`, `kill-process`, `block-ip` | Automated action playbook to trigger upon ingest. |
| `x-localobserve-remediation-link` | `string` | `https://github.com/JJediny/LocalObserve/blob/main/docs/troubleshooting.md` | Runbook or remediation documentation URI. |
| `x-localobserve-github-pr` | `string` | `PR #64`, `fix/rsigma-healthcheck-and-alert-validation` | Related GitHub PR or branch context. |

---

## 2. All-Features Alert Payload Example

The example below demonstrates a fully compliant alert payload exercising all standard fields and custom `x-` extensions:

```json
{
  "timestamp": "2026-08-24T22:30:00Z",
  "alert_name": "Suspicious Namespace Unshare Command",
  "severity": "high",
  "description": "Rule ID: 718c5dbc-b1a3-419b-a329-e7721d294257 triggered. Unprivileged user executed 'unshare --user --map-root-user /bin/bash'.",
  "source": "rsigma",
  "title": "LocalObserve Alert: Suspicious Namespace Unshare Command",
  "body": "Unprivileged user executed unshare mapped to root user [Severity: high]",
  "x-localobserve-source-component": "rsigma-detector",
  "x-localobserve-mitre-tactic": "TA0004-privilege-escalation",
  "x-localobserve-mitre-technique": "T1068",
  "x-localobserve-action-playbook": "desktop-notify",
  "x-localobserve-remediation-link": "https://github.com/JJediny/LocalObserve/blob/main/docs/runtimes_alerting_and_resource_guide.md",
  "x-localobserve-github-pr": "PR #64 (fix/rsigma-healthcheck-and-alert-validation)"
}
```

---

## 3. Automated Action Playbooks & GitHub Actions Integration

Alert payloads containing `x-localobserve-action-playbook` are mapped to automated remediation tasks in LocalObserve:

```bash
# 1. Dispatch full-featured test alert payload to alert-receiver
curl -s -X POST http://localhost:9000/hooks/security-alert-open \
  -H "Content-Type: application/json" \
  -d '{
    "alert_name": "Sensitive File Read (/proc/kallsyms)",
    "severity": "critical",
    "description": "Non-root process executed read on /proc/kallsyms",
    "x-localobserve-source-component": "falco-ebpf",
    "x-localobserve-mitre-tactic": "TA0007-discovery",
    "x-localobserve-mitre-technique": "T1068",
    "x-localobserve-action-playbook": "desktop-notify",
    "x-localobserve-github-pr": "fix/rsigma-healthcheck-and-alert-validation"
  }'

# 2. Trigger native visual desktop alert
task notify-desktop-replay
```

### GitHub Actions CI Workflow Mapping
The GitHub Actions workflow at [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) executes static rule validation, Compose config rendering, and lockfile integrity checks automatically on pull request pushes.

---

## 4. Libre Project Links & Open PR References

### Open Libre Software Subsystem Links

- 🦅 **Falco (CNCF)**: [Falcosecurity Engine & Rule Specs](https://github.com/falcosecurity/falco)
- 🦭 **osquery (Linux Foundation)**: [osquery System Telemetry Tables](https://github.com/osquery/osquery)
- ⚡ **rsigma (Timescale)**: [rsigma Rust Streaming Engine](https://github.com/timescale/rsigma)
- 📊 **OpenObserve (Zinclabs)**: [OpenObserve Cloud-Native Telemetry Engine](https://github.com/openobserve/openobserve)

### Active Repository PRs & Feature Branches

- 🔀 **Current Active Branch**: [`fix/rsigma-healthcheck-and-alert-validation`](Taskfile.yml) — Healthchecks, webhook receiver integration, desktop notifier & payload schema validation.
- 🔀 **Open PR #64**: `feat/otelcol-mise-validation` — OpenTelemetry Collector toolchain integration & `mise` lockfile validation.
- 🔀 **Feature Branch**: `remotes/origin/rsigma-daemon-integration` — Daemonized streaming Sigma detection pipeline.
- 🔀 **Feature Branch**: `remotes/origin/feat/falco-validation-and-threat-intel` — Falco 0.43.1 ruleset validation and YARA threat intel sync.
- 🔀 **Feature Branch**: `remotes/origin/container-modernization` — Multi-runtime container modernization across Docker, Podman, and Nerdctl.

---

## 5. Troubleshooting & Schema Validation Links

- 📐 **[JSON Schema Source](../schemas/alert_payload_schema.json)** — Official JSON Schema Draft 2020-12 alert specification.
- 🛠️ **[Troubleshooting Guide](./troubleshooting.md)** — Alert receiver HTTP status codes and webhook debugging.
- 🌐 **[Multi-Runtime & Alerting Guide](./runtimes_alerting_and_resource_guide.md)** — Multi-runtime deployment and desktop notification daemon setup.
- 💻 **[IDE Debugging & OTEL Adapters Guide](./ide_debugging_and_otel_adapters.md)** — Step-by-step OTLP exporter setup for IDE debuggers and language SDKs.
