import json
from pathlib import Path
import pytest

SCHEMA_PATH = Path("schemas/alert_payload_schema.json")


def load_schema():
    assert SCHEMA_PATH.exists(), f"Schema file missing at {SCHEMA_PATH}"
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_alert_payload(payload: dict):
    schema = load_schema()
    # Check required fields
    for field in schema.get("required", []):
        assert field in payload, f"Missing required field: {field}"

    # Check severity enum
    valid_severities = schema["properties"]["severity"]["enum"]
    assert payload["severity"] in valid_severities, f"Invalid severity: {payload['severity']}"

    # Check x-localobserve-source-component enum if present
    if "x-localobserve-source-component" in payload:
        valid_sources = schema["properties"]["x-localobserve-source-component"]["enum"]
        assert payload["x-localobserve-source-component"] in valid_sources

    # Check x-localobserve-action-playbook enum if present
    if "x-localobserve-action-playbook" in payload:
        valid_playbooks = schema["properties"]["x-localobserve-action-playbook"]["enum"]
        assert payload["x-localobserve-action-playbook"] in valid_playbooks


def test_schema_valid_file_exists():
    schema = load_schema()
    assert schema["title"] == "LocalObserve Security Alert Payload Schema"
    assert "x-localobserve-source-component" in schema["properties"]
    assert "x-localobserve-action-playbook" in schema["properties"]
    assert "x-localobserve-github-pr" in schema["properties"]


def test_full_featured_payload_validation():
    sample_payload = {
        "timestamp": "2026-08-24T22:30:00Z",
        "alert_name": "Suspicious Namespace Unshare Command",
        "severity": "high",
        "description": "Rule ID: 718c5dbc-b1a3-419b-a329-e7721d294257 triggered. Unprivileged user executed unshare",
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

    validate_alert_payload(sample_payload)


def test_invalid_severity_raises():
    bad_payload = {
        "alert_name": "Test Alert",
        "severity": "super-critical-invalid",
        "description": "Test"
    }
    with pytest.raises(AssertionError, match="Invalid severity"):
        validate_alert_payload(bad_payload)


def test_missing_required_raises():
    incomplete_payload = {
        "severity": "high",
        "description": "Missing alert_name"
    }
    with pytest.raises(AssertionError, match="Missing required field: alert_name"):
        validate_alert_payload(incomplete_payload)
