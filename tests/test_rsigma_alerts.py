"""test_rsigma_alerts.py

Validates the rsigma → alert-receiver detection pipeline end-to-end.

Integration tests (behind ``--run-stack``) send events to rsigma's HTTP
API and verify:
  * Detection matches fire
  * Webhook payload reaches alert-receiver
  * Alert JSON files are created with correct fields
  * Edge cases (benign events, multi-event batching)

Unit tests validate configuration files without a running stack.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

import pytest
import requests
import yaml

# ---------------------------------------------------------------------------
# shared markers / helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]

RSIGMA_URL = os.environ.get("RSIGMA_URL", "http://localhost:9090")
ALERT_RECEIVER_URL = os.environ.get("ALERT_RECEIVER_URL", "http://localhost:9000")
ALERT_DIR = Path(".data/alerts")
COMPOSE_CMD = os.environ.get("COMPOSE_CMD", "docker compose").split()
COMPOSE_PROJECT = os.environ.get("COMPOSE_PROJECT", "localobserve-dev")


def _compose(*args: str) -> list[str]:
    """Build a compose command list for the current runtime.

    Uses ``COMPOSE_CMD`` env var (defaults to ``docker compose``) so tests
    work across Docker, Podman, and Nerdctl without code changes.

    Usage::

        COMPOSE_CMD="podman compose" pytest --run-stack tests/test_rsigma_alerts.py
    """
    return [*COMPOSE_CMD, "-p", COMPOSE_PROJECT, *args]

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rigma_base() -> str:
    """Wait for rsigma to be reachable and return the base URL."""
    timeout = 30
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{RSIGMA_URL}/api/v1/status", timeout=3)
            if r.status_code == 200:
                return RSIGMA_URL
        except requests.RequestException:
            pass
        time.sleep(1)
    pytest.fail(f"rsigma not reachable at {RSIGMA_URL} within {timeout}s")


@pytest.fixture(scope="module")
def rsigma_initial_status(rigma_base: str) -> dict:
    """Snapshot of rsigma status before tests run."""
    r = requests.get(f"{rigma_base}/api/v1/status", timeout=5)
    assert r.status_code == 200
    return r.json()


def _send_event(url: str, payload: dict, *, timeout: int = 5) -> dict:
    """POST a JSON event to rsigma and return the response body."""
    r = requests.post(
        f"{url}/api/v1/events",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    assert r.status_code == 200, f"rsigma rejected event: {r.text}"
    return r.json()


def _load_yaml(relative: str) -> dict:
    return yaml.safe_load((REPO_ROOT / relative).read_text(encoding="utf-8"))


# ===================================================================
# Integration tests (require --run-stack)
# ===================================================================


@pytest.mark.integration
class TestRsigmaEventIngestion:
    """Basic event-ingestion checks."""

    def test_api_accepts_valid_event(self, rigma_base: str) -> None:
        """POST a minimal valid event — rsigma must accept it."""
        resp = _send_event(rigma_base, {
            "name": "unshare",
            "cmdline": "unshare --user /bin/sh",
            "pid": 10001,
        })
        assert resp.get("accepted") == 1, f"Expected accepted=1, got {resp}"

    def test_api_handles_non_json_content_type(self, rigma_base: str) -> None:
        """rsigma must handle (accept or reject) non-JSON Content-Type gracefully.

        rsigma 0.19.0 accepts text/plain and returns 200 — this test verifies
        the server does not crash or hang on unexpected content types.
        """
        r = requests.post(
            f"{rigma_base}/api/v1/events",
            data="not json",
            headers={"Content-Type": "text/plain"},
            timeout=5,
        )
        # Any non-5xx response is acceptable — the server must not crash.
        assert r.status_code < 500, (
            f"rsigma crashed on non-JSON body: {r.status_code} {r.text}"
        )

    def test_events_increment_processed_counter(
        self, rigma_base: str, rsigma_initial_status: dict
    ) -> None:
        """Sending events must increase the events_processed counter."""
        before = rsigma_initial_status.get("events_processed", 0)
        for i in range(3):
            _send_event(rigma_base, {
                "name": "unshare",
                "cmdline": f"unshare --user test_{i}",
                "pid": 20000 + i,
            })
        time.sleep(2)
        r = requests.get(f"{rigma_base}/api/v1/status", timeout=5)
        after = r.json().get("events_processed", 0)
        assert after >= before + 3, (
            f"events_processed should be ≥{before + 3}, got {after}"
        )


@pytest.mark.integration
class TestSuspiciousUnshareDetection:
    """Tests for the Suspicious Namespace Unshare Command Sigma rule."""

    MATCHING_EVENT = {
        "name": "unshare",
        "cmdline": "unshare --user --map-root-user /bin/bash",
        "pid": 22222,
    }

    BENIGN_EVENT = {
        "name": "unshare",
        "cmdline": "unshare --mount --pid /bin/bash",
        "pid": 33333,
    }

    def test_detection_fires_on_matching_event(
        self, rigma_base: str, rsigma_initial_status: dict
    ) -> None:
        """Event with unshare --user must trigger the detection rule."""
        before = rsigma_initial_status.get("detection_matches", 0)
        _send_event(rigma_base, self.MATCHING_EVENT)
        time.sleep(2)
        r = requests.get(f"{rigma_base}/api/v1/status", timeout=5)
        after = r.json().get("detection_matches", 0)
        assert after > before, (
            f"detection_matches should increase from {before}, got {after}"
        )

    def test_benign_unshare_does_not_trigger(
        self, rigma_base: str
    ) -> None:
        """unshare without --user/--map-root-user must NOT fire the rule."""
        r = requests.get(f"{rigma_base}/api/v1/status", timeout=5)
        before = r.json().get("detection_matches", 0)
        _send_event(rigma_base, self.BENIGN_EVENT)
        time.sleep(2)
        r = requests.get(f"{rigma_base}/api/v1/status", timeout=5)
        after = r.json().get("detection_matches", 0)
        # The benign event should not increase detection_matches.
        assert after == before, (
            f"Benign unshare should NOT trigger detection; "
            f"before={before}, after={after}"
        )

    def test_event_with_wrong_process_name_no_match(
        self, rigma_base: str
    ) -> None:
        """Event with correct cmdline but wrong ProcessName must not match."""
        r = requests.get(f"{rigma_base}/api/v1/status", timeout=5)
        before = r.json().get("detection_matches", 0)
        _send_event(rigma_base, {
            "name": "bash",  # not "unshare"
            "cmdline": "unshare --user /bin/sh",
            "pid": 44444,
        })
        time.sleep(2)
        r = requests.get(f"{rigma_base}/api/v1/status", timeout=5)
        after = r.json().get("detection_matches", 0)
        assert after == before, (
            "Event with name=bash should NOT match the unshare rule"
        )


@pytest.mark.integration
class TestWebhookAndAlertReceiver:
    """End-to-end: rsigma detection → webhook → alert-receiver → file."""

    # Each test uses a unique pid so rsigma does not coalesce events.
    _pid_counter = 60000

    @staticmethod
    def _next_pid() -> int:
        TestWebhookAndAlertReceiver._pid_counter += 1
        return TestWebhookAndAlertReceiver._pid_counter

    def _matching_event(self) -> dict:
        return {
            "name": "unshare",
            "cmdline": "unshare --map-root-user /bin/sh",
            "pid": self._next_pid(),
        }

    @pytest.fixture(autouse=True)
    def _ensure_dir(self) -> None:
        ALERT_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # helpers that read alert files from *inside* the container to avoid
    # host-volume propagation timing issues.
    # ------------------------------------------------------------------
    @staticmethod
    def _container_alert_files() -> list[str]:
        import subprocess
        result = subprocess.run(
            [*_compose("exec", "-T", "alert-receiver", "ls", "-1", "/var/log/alerts/")],
            capture_output=True, text=True, timeout=10,
            cwd=str(REPO_ROOT),
        )
        result.check_returncode()
        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

    @staticmethod
    def _read_container_alert_file(filename: str) -> dict:
        import subprocess
        result = subprocess.run(
            [*_compose("exec", "-T", "alert-receiver", "cat", f"/var/log/alerts/{filename}")],
            capture_output=True, text=True, timeout=10,
            cwd=str(REPO_ROOT),
        )
        result.check_returncode()
        return json.loads(result.stdout)

    def test_webhook_delivers_and_alert_file_is_valid(
        self, rigma_base: str
    ) -> None:
        """End-to-end: detection → webhook → alert file with correct fields.

        Verifies:
        * A new alert JSON file appears in /var/log/alerts/ after detection.
        * The file contains alert_name, severity, description, and title.
        * The timestamp is a valid ISO-8601 string.
        """
        before = set(self._container_alert_files())
        _send_event(rigma_base, self._matching_event())

        deadline = time.time() + 20
        new_file = None
        while time.time() < deadline:
            after = set(self._container_alert_files())
            new = after - before
            if new:
                new_file = new.pop()
                break
            time.sleep(0.5)

        assert new_file is not None, (
            "No new alert file appeared in container /var/log/alerts/"
        )

        data = self._read_container_alert_file(new_file)

        # Required fields
        assert data.get("alert_name") == "Suspicious Namespace Unshare Command", (
            f"Unexpected alert_name: {data.get('alert_name')}"
        )
        assert data.get("severity") == "high", (
            f"Expected severity=high, got {data.get('severity')}"
        )
        assert "718c5dbc" in data.get("description", ""), (
            f"Description should contain rule ID, got: {data.get('description')}"
        )
        assert "LocalObserve Alert" in data.get("title", ""), (
            f"Title should mention LocalObserve, got: {data.get('title')}"
        )

        # Timestamp must be ISO-8601
        ts = data.get("timestamp", "")
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]", ts), (
            f"Timestamp not ISO-8601: {ts}"
        )

    def test_alert_receiver_reachable(self) -> None:
        """Alert-receiver must respond to HTTP requests."""
        try:
            r = requests.get(ALERT_RECEIVER_URL, timeout=3)
            assert r.status_code in (200, 404), (
                f"Alert receiver returned {r.status_code}"
            )
        except requests.RequestException as exc:
            pytest.fail(f"Alert receiver not reachable: {exc}")


# ===================================================================
# Unit tests (no stack required — config-only validation)
# ===================================================================


class TestSigmaRuleStructure:
    """Validate the active Sigma detection rule file."""

    def test_rule_has_valid_uuid_id(self) -> None:
        """Rule ID must be a valid UUID v4."""
        rule_path = REPO_ROOT / "rules" / "sigma" / "active_rules" / "suspicious_unshare.yaml"
        assert rule_path.exists(), f"Rule file not found: {rule_path}"
        rule = yaml.safe_load(rule_path.read_text())
        rule_id = rule.get("id", "")
        uuid_re = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        assert re.match(uuid_re, rule_id, re.IGNORECASE), f"Invalid UUID: {rule_id}"

    def test_rule_has_required_metadata(self) -> None:
        """Rule must include title, level, status, description, and logsource."""
        rule_path = REPO_ROOT / "rules" / "sigma" / "active_rules" / "suspicious_unshare.yaml"
        rule = yaml.safe_load(rule_path.read_text())
        for field in ("title", "level", "status", "description", "logsource"):
            assert rule.get(field), f"Rule missing required field: {field}"

    def test_rule_detection_has_condition(self) -> None:
        """Detection block must have a condition and at least one selection."""
        rule_path = REPO_ROOT / "rules" / "sigma" / "active_rules" / "suspicious_unshare.yaml"
        rule = yaml.safe_load(rule_path.read_text())
        detection = rule.get("detection", {})
        assert "condition" in detection, "Detection block missing 'condition'"
        assert len(detection) >= 2, (
            "Detection should have condition + at least 1 selection"
        )

    def test_rule_logsource_matches_pipeline(self) -> None:
        """Rule logsource must match a pipeline mapping (osquery or falco)."""
        rule_path = REPO_ROOT / "rules" / "sigma" / "active_rules" / "suspicious_unshare.yaml"
        rule = yaml.safe_load(rule_path.read_text())
        ls = rule.get("logsource", {})
        assert ls.get("product") == "linux"
        assert ls.get("service") in ("osquery", "falco"), (
            f"Unsupported logsource service: {ls.get('service')}"
        )


class TestPipelineMappings:
    """Validate field-name mapping pipelines."""

    def test_osquery_pipeline_maps_processname_to_name(self) -> None:
        """Pipeline must map ProcessName → name for osquery events."""
        pipeline = _load_yaml("rules/sigma/pipelines/localobserve_pipeline.yaml")
        transforms = pipeline.get("transformations", [])
        osquery_tx = [t for t in transforms if "osquery" in str(t.get("id", ""))]
        assert osquery_tx, "No osquery field mapping found"
        mapping = osquery_tx[0].get("mapping", {})
        assert mapping.get("ProcessName") == "name", (
            f"ProcessName should map to name, got: {mapping.get('ProcessName')}"
        )
        assert mapping.get("CommandLine") == "cmdline", (
            f"CommandLine should map to cmdline, got: {mapping.get('CommandLine')}"
        )
        assert mapping.get("ProcessId") == "pid", (
            f"ProcessId should map to pid, got: {mapping.get('ProcessId')}"
        )

    def test_falco_pipeline_maps_commandline(self) -> None:
        """Pipeline must map CommandLine → output_fields.proc.cmdline for falco."""
        pipeline = _load_yaml("rules/sigma/pipelines/localobserve_pipeline.yaml")
        transforms = pipeline.get("transformations", [])
        falco_tx = [t for t in transforms if "falco" in str(t.get("id", ""))]
        assert falco_tx, "No falco field mapping found"
        mapping = falco_tx[0].get("mapping", {})
        assert "CommandLine" in mapping, "Falco pipeline should map CommandLine"
        assert "output_fields" in mapping.get("CommandLine", ""), (
            f"Falco CommandLine should map to output_fields, got: {mapping.get('CommandLine')}"
        )


class TestWebhookConfig:
    """Validate rsigma webhook configuration."""

    def test_webhook_has_content_type_header(self) -> None:
        """Webhook must set Content-Type: application/json."""
        cfg = _load_yaml("rules/sigma/webhooks/alert_receiver.yaml")
        hooks = cfg.get("webhooks", [])
        assert hooks, "No webhooks defined"
        headers = hooks[0].get("headers", {})
        assert headers.get("Content-Type") == "application/json"

    def test_webhook_body_has_template_variables(self) -> None:
        """Webhook body must use rsigma template variables for field substitution."""
        cfg = _load_yaml("rules/sigma/webhooks/alert_receiver.yaml")
        hooks = cfg.get("webhooks", [])
        body = hooks[0].get("body", "")
        for var in ("detection.rule.title", "detection.rule.level", "detection.rule.id"):
            assert f"${{{var}}}" in body, (
                f"Webhook body missing template variable: {var}"
            )

    def test_webhook_kind_is_detection(self) -> None:
        """rsigma webhook kind must be 'detection' to fire on rule matches."""
        cfg = _load_yaml("rules/sigma/webhooks/alert_receiver.yaml")
        hooks = cfg.get("webhooks", [])
        assert hooks[0].get("kind") == "detection", (
            f"Webhook kind should be 'detection', got: {hooks[0].get('kind')}"
        )
