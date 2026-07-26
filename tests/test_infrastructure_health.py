from __future__ import annotations

"""
test_infrastructure_health.py

Validates infrastructure health monitoring configuration:
1. Docker Compose healthchecks are defined for critical services
2. Health monitor script exists and is executable
3. Notification channels are properly configured
"""

import json
import stat
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_compose() -> dict:
    return yaml.safe_load((REPO_ROOT / "docker-compose.yaml").read_text())


def test_compose_has_healthchecks_for_critical_services() -> None:
    """Critical services must have Docker healthchecks defined."""
    compose = _load_compose()
    services = compose.get("services", {})

    critical_services = {"falco", "openobserve", "otel-collector", "alert-receiver", "rsigma"}
    for svc_name in critical_services:
        svc = services.get(svc_name, {})
        assert "healthcheck" in svc, (
            f"Service '{svc_name}' missing healthcheck definition"
        )
        hc = svc["healthcheck"]
        assert "test" in hc, f"Service '{svc_name}' healthcheck missing test command"
        assert "interval" in hc, f"Service '{svc_name}' healthcheck missing interval"
        assert "retries" in hc, f"Service '{svc_name}' healthcheck missing retries"


def test_health_monitor_script_exists() -> None:
    """Health monitor script must exist in tools/."""
    script = REPO_ROOT / "tools" / "health-monitor.sh"
    assert script.exists(), "health-monitor.sh not found in tools/"


def test_health_monitor_script_is_executable() -> None:
    """Health monitor script must be executable."""
    script = REPO_ROOT / "tools" / "health-monitor.sh"
    if script.exists():
        mode = script.stat().st_mode
        assert mode & stat.S_IXUSR, "health-monitor.sh not executable by owner"


def test_health_monitor_has_disk_space_checks() -> None:
    """Health monitor must include disk space monitoring."""
    script = (REPO_ROOT / "tools" / "health-monitor.sh").read_text()
    assert "DISK_WARN_PERCENT" in script
    assert "DISK_CRIT_PERCENT" in script
    assert "df " in script


def test_health_monitor_has_dead_mans_switch() -> None:
    """Health monitor must implement a dead man's switch."""
    script = (REPO_ROOT / "tools" / "health-monitor.sh").read_text()
    assert "heartbeat" in script.lower()
    assert "HEARTBEAT_MAX_AGE" in script


def test_health_monitor_checks_all_services() -> None:
    """Health monitor must check required services and account for optional scan services."""
    script = (REPO_ROOT / "tools" / "health-monitor.sh").read_text()
    for svc in ("falco", "openobserve", "otel-collector", "rsigma"):
        assert svc in script, f"Health monitor should check {svc}"
    for svc in ("clamav", "clamav-scanner"):
        assert svc in script, f"Health monitor should mention optional service {svc}"


def test_compose_marks_clamav_services_optional_via_scan_profile() -> None:
    """ClamAV services should be opt-in so the core stack stays lightweight."""
    compose = _load_compose()
    services = compose.get("services", {})

    for svc_name in ("clamav", "clamav-scanner"):
        svc = services.get(svc_name, {})
        assert svc.get("profiles") == ["scan"], (
            f"Service '{svc_name}' should be gated behind the scan profile"
        )


def test_notify_script_supports_slack() -> None:
    """Notification script must support Slack webhooks."""
    script = (REPO_ROOT / "alerts" / "webhook" / "notify.sh").read_text()
    assert "SLACK_WEBHOOK_URL" in script
    assert "curl" in script


def test_notify_script_supports_email() -> None:
    """Notification script must support email notifications."""
    script = (REPO_ROOT / "alerts" / "webhook" / "notify.sh").read_text()
    assert "EMAIL_TO" in script
    assert "mail " in script


def test_notify_script_supports_generic_webhook() -> None:
    """Notification script must support generic webhooks (PagerDuty, Discord, etc.)."""
    script = (REPO_ROOT / "alerts" / "webhook" / "notify.sh").read_text()
    assert "GENERIC_WEBHOOK_URL" in script


def test_compose_exposes_notification_env_vars() -> None:
    """Docker Compose must expose notification channel environment variables."""
    compose = _load_compose()
    alert_receiver = compose.get("services", {}).get("alert-receiver", {})
    env = alert_receiver.get("environment", [])

    env_keys = [e.split("=")[0] for e in env if "=" in e or ":" not in e]
    env_vars = " ".join(env)

    assert "SLACK_WEBHOOK_URL" in env_vars
    assert "EMAIL_TO" in env_vars
    assert "GENERIC_WEBHOOK_URL" in env_vars


def test_alerts_json_has_system_log_alerts() -> None:
    """Alert definitions must include system-log based alerts (auth, sudo)."""
    alerts_file = REPO_ROOT / "alerts" / "openobserve" / "alerts.json"
    alerts = json.loads(alerts_file.read_text())

    system_log_alerts = [a for a in alerts if a.get("stream_name") == "system-logs"]
    assert len(system_log_alerts) >= 2, (
        "Expected at least 2 system-logs alerts (auth failure, sudo abuse)"
    )

    alert_names = {a["name"] for a in system_log_alerts}
    assert "SystemLogs-Auth-Failure-Spike" in alert_names
    assert "SystemLogs-Sudo-Abuse" in alert_names


def test_alerts_json_has_osquery_persistence_alerts() -> None:
    """Alert definitions must include OSquery-based persistence detection."""
    alerts_file = REPO_ROOT / "alerts" / "openobserve" / "alerts.json"
    alerts = json.loads(alerts_file.read_text())

    osquery_alerts = [a for a in alerts if a.get("stream_name") == "osquery"]
    alert_names = {a["name"] for a in osquery_alerts}

    assert "OSquery-New-Cron-Job" in alert_names
    assert "OSquery-SUID-Binary-Added" in alert_names
    assert "OSquery-New-Systemd-Unit" in alert_names
    assert "OSquery-New-User-Account" in alert_names


def test_alerts_json_clamav_uses_correct_field() -> None:
    """ClamAV alert must use scan_status (not status) to match OTEL parser output."""
    alerts_file = REPO_ROOT / "alerts" / "openobserve" / "alerts.json"
    alerts = json.loads(alerts_file.read_text())

    clamav_alert = None
    for a in alerts:
        if a.get("name") == "ClamAV-Malware-FOUND":
            clamav_alert = a
            break

    assert clamav_alert is not None, "ClamAV-Malware-FOUND alert not found"
    sql = clamav_alert["query_condition"]["sql"]
    assert "scan_status" in sql, "ClamAV alert should use 'scan_status' field"
    assert " scan_status = 'FOUND'" in sql, "ClamAV alert should use 'scan_status = FOUND'"
