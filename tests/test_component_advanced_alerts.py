"""
test_component_advanced_alerts.py - Verification suite testing advanced alert payloads for all logging components:
- Falco (Kernel eBPF / Syscall Security)
- osquery (System State & Process Telemetry)
- rsigma (Streaming Sigma Threat Detections)
- OTel Collector (OpenTelemetry Traces & OTTL Transformations)

Each payload incorporates the localhost OpenObserve link (http://localhost:5080) and x- vendor extensions.
"""

import json
from pathlib import Path
import pytest

SCHEMA_PATH = Path("schemas/alert_payload_schema.json")
OPENOBSERVE_UI_URL = "http://localhost:5080/default/logs"


def load_schema():
    assert SCHEMA_PATH.exists(), f"Schema missing at {SCHEMA_PATH}"
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_advanced_payload(payload: dict, expected_component: str):
    schema = load_schema()
    # Required fields check
    for field in schema["required"]:
        assert field in payload, f"Missing required field: {field}"

    # Severity check
    assert payload["severity"] in schema["properties"]["severity"]["enum"]

    # Source component check
    assert payload.get("x-localobserve-source-component") == expected_component
    assert payload.get("x-localobserve-source-component") in schema["properties"]["x-localobserve-source-component"]["enum"]

    # OpenObserve UI link check
    assert "openobserve_url" in payload or "x-localobserve-remediation-link" in payload
    oo_url = payload.get("openobserve_url") or payload.get("x-localobserve-remediation-link")
    assert "localhost:5080" in oo_url, f"Missing localhost OpenObserve UI link in payload: {oo_url}"


def test_falco_advanced_alert_payload():
    falco_payload = {
        "timestamp": "2026-08-24T23:00:00Z",
        "alert_name": "Falco: Shell Spawned in Privileged Container",
        "severity": "critical",
        "description": "Rule ID: falco-0041. Process /bin/bash spawned inside privileged container app-db-1.",
        "source": "falco",
        "openobserve_url": "http://localhost:5080/default/logs?stream=falco_events",
        "x-localobserve-source-component": "falco-ebpf",
        "x-localobserve-mitre-tactic": "TA0004-privilege-escalation",
        "x-localobserve-mitre-technique": "T1068",
        "x-localobserve-action-playbook": "isolate-container",
        "x-localobserve-remediation-link": "http://localhost:5080/default/logs",
        "x-localobserve-github-pr": "fix/rsigma-healthcheck-and-alert-validation"
    }

    validate_advanced_payload(falco_payload, "falco-ebpf")


def test_osquery_advanced_alert_payload():
    osquery_payload = {
        "timestamp": "2026-08-24T23:01:00Z",
        "alert_name": "osquery: Unauthorized Sudoers File Modification",
        "severity": "high",
        "description": "Table: file_events. Path /etc/sudoers.d/99-backdoor modified by uid=1000.",
        "source": "osquery",
        "openobserve_url": "http://localhost:5080/default/logs?stream=osquery_events",
        "x-localobserve-source-component": "osquery-daemon",
        "x-localobserve-mitre-tactic": "TA0005-defense-evasion",
        "x-localobserve-mitre-technique": "T1548.003",
        "x-localobserve-action-playbook": "desktop-notify",
        "x-localobserve-remediation-link": "http://localhost:5080/default/logs",
        "x-localobserve-github-pr": "fix/rsigma-healthcheck-and-alert-validation"
    }

    validate_advanced_payload(osquery_payload, "osquery-daemon")


def test_rsigma_advanced_alert_payload():
    rsigma_payload = {
        "timestamp": "2026-08-24T23:02:00Z",
        "alert_name": "rsigma: Suspicious Namespace Unshare Command",
        "severity": "high",
        "description": "Sigma Rule: 718c5dbc-b1a3-419b-a329-e7721d294257. Mapped user unshare to root.",
        "source": "rsigma",
        "openobserve_url": "http://localhost:5080/default/logs?stream=rsigma_alerts",
        "x-localobserve-source-component": "rsigma-detector",
        "x-localobserve-mitre-tactic": "TA0004-privilege-escalation",
        "x-localobserve-mitre-technique": "T1059.004",
        "x-localobserve-action-playbook": "kill-process",
        "x-localobserve-remediation-link": "http://localhost:5080/default/logs",
        "x-localobserve-github-pr": "fix/rsigma-healthcheck-and-alert-validation"
    }

    validate_advanced_payload(rsigma_payload, "rsigma-detector")


def test_otelcol_advanced_alert_payload():
    otelcol_payload = {
        "timestamp": "2026-08-24T23:03:00Z",
        "alert_name": "OTel Collector: OTTL High Log Error Rate Anomaly",
        "severity": "medium",
        "description": "OTTL Processor: Error rate exceeded threshold (>50 err/sec) on app-gateway-service.",
        "source": "otelcol",
        "openobserve_url": "http://localhost:5080/default/logs?stream=otel_logs",
        "x-localobserve-source-component": "otelcol-processor",
        "x-localobserve-mitre-tactic": "TA0040-impact",
        "x-localobserve-mitre-technique": "T1499",
        "x-localobserve-action-playbook": "audit-log-only",
        "x-localobserve-remediation-link": "http://localhost:5080/default/logs",
        "x-localobserve-github-pr": "PR #64 (feat/otelcol-mise-validation)"
    }

    validate_advanced_payload(otelcol_payload, "otelcol-processor")
