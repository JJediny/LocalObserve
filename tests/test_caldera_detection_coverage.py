from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from tests.caldera_coverage_support import PAYLOAD_ABILITY
from tests.caldera_coverage_support import SAFE_ABILITIES
from tests.caldera_coverage_support import AVOID_LOGS_ABILITY
from tests.caldera_coverage_support import DUMP_HISTORY_ABILITY
from tests.caldera_coverage_support import build_coverage_report
from tests.caldera_coverage_support import write_coverage_report
from tests.caldera_coverage_support import validate_stream_schema
from tests.caldera_coverage_support import REQUIRED_STREAM_SCHEMA_FIELDS


pytestmark = [pytest.mark.integration, pytest.mark.host_emulation]

# ---------------------------------------------------------------------------
# Configurable timeouts via environment variables
# ---------------------------------------------------------------------------
TRACE_VERIFY_TIMEOUT = int(os.environ.get("CALDERA_TRACE_VERIFY_TIMEOUT", "90"))
LOG_VERIFY_TIMEOUT = int(os.environ.get("CALDERA_LOG_VERIFY_TIMEOUT", "90"))
TRACE_VERIFY_INTERVAL = int(os.environ.get("CALDERA_TRACE_VERIFY_INTERVAL", "2"))
LOG_VERIFY_INTERVAL = int(os.environ.get("CALDERA_LOG_VERIFY_INTERVAL", "2"))
ABILITY_EXECUTION_TIMEOUT = int(os.environ.get("CALDERA_ABILITY_TIMEOUT", "30"))

# Retry configuration: how many times to retry a failing ability from scratch
MAX_ABILITY_RETRIES = int(os.environ.get("CALDERA_MAX_RETRIES", "3"))



def _run(
    repo_root: Path,
    args: list[str],
    *,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess, optionally with a custom timeout."""
    kwargs: dict[str, Any] = {
        "cwd": repo_root,
        "check": True,
        "capture_output": True,
        "text": True,
    }
    if timeout is not None:
        kwargs["timeout"] = timeout
    return subprocess.run(args, **kwargs)


def _run_ability(
    repo_root: Path,
    ability_id: str,
    *,
    retries: int = MAX_ABILITY_RETRIES,
) -> dict:
    """Run a CALDERA ability via the harness with configurable timeouts and retry logic.

    Retries on failure (non-zero exit or verification timeout) up to *retries* times.
    Each retry re-bootstraps the CALDERA repo and re-executes the ability with the
    configured verification timeouts.
    """
    harness_args = [
        "uv",
        "run",
        "python",
        "tools/caldera_otel_harness.py",
        "run-ability",
        "--bootstrap",
        "--ability-id",
        ability_id,
        "--verify-trace",
        "--verify-logs",
        "--verify-timeout-seconds",
        str(TRACE_VERIFY_TIMEOUT),
        "--verify-interval-seconds",
        str(TRACE_VERIFY_INTERVAL),
        "--log-verify-timeout-seconds",
        str(LOG_VERIFY_TIMEOUT),
        "--log-verify-interval-seconds",
        str(LOG_VERIFY_INTERVAL),
        "--timeout-seconds",
        str(ABILITY_EXECUTION_TIMEOUT),
    ]

    last_exc: Exception | None = None
    last_payload: dict[str, Any] | None = None

    for attempt in range(1, retries + 1):
        try:
            result = _run(repo_root, harness_args, timeout=ABILITY_EXECUTION_TIMEOUT + TRACE_VERIFY_TIMEOUT + LOG_VERIFY_TIMEOUT + 30)
            payload = json.loads(result.stdout)
            last_payload = payload

            # If the ability ran but verification failed, log and retry
            if payload["exit_code"] != 0:
                if attempt < retries:
                    _diagnostic_log(ability_id, attempt, f"non-zero exit_code={payload['exit_code']}; retrying")
                    time.sleep(1)
                    continue

            # If trace verification failed, log and retry
            if not payload["trace"].get("verified"):
                if attempt < retries:
                    _diagnostic_log(ability_id, attempt, f"trace not verified; retrying")
                    time.sleep(2)
                    continue

            # If falco correlation is expected but not verified, log and retry
            correlation = payload.get("correlation", {})
            if correlation.get("expected_count", 0) > 0 and not correlation.get("verified"):
                if attempt < retries:
                    _diagnostic_log(ability_id, attempt, f"correlation not verified ({correlation.get('verified_count', 0)}/{correlation.get('expected_count', 0)}); retrying")
                    time.sleep(3)
                    continue

            return payload

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt < retries:
                _diagnostic_log(ability_id, attempt, f"exception: {exc}; retrying")
                time.sleep(2)

    # All retries exhausted — return last payload if available, otherwise raise
    if last_payload is not None:
        return last_payload
    raise last_exc or RuntimeError(f"ability {ability_id} failed after {retries} retries with no payload")


def _diagnostic_log(ability_id: str, attempt: int, message: str) -> None:
    """Print a diagnostic log line for retry attempts."""
    print(f"[CALDERA-RETRY] ability={ability_id} attempt={attempt} {message}")


# ---------------------------------------------------------------------------
# Telemetry stream schema validation helpers
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Enhanced assertion helpers with diagnostic output
# ---------------------------------------------------------------------------
def _assert_trace_verified(payload: dict, ability_id: str) -> None:
    """Assert trace verification succeeded with a detailed error on failure."""
    trace = payload.get("trace", {})
    if trace.get("verified"):
        return
    hits = trace.get("hits", [])
    trace_id = trace.get("trace_id", "<missing>")
    raise AssertionError(
        f"Trace verification failed for ability {ability_id}:\n"
        f"  trace_id: {trace_id}\n"
        f"  expected: trace to be searchable in OpenObserve\n"
        f"  found: {len(hits)} hit(s)\n"
        f"  raw trace data: {json.dumps(trace, indent=2, default=str)[:2000]}"
    )


def _assert_falco_correlation(payload: dict, ability_id: str) -> None:
    """Assert Falco log correlation succeeded with a detailed error on failure."""
    correlation = payload.get("correlation", {})
    streams = correlation.get("streams", {})
    falco = streams.get("falco", {})
    if falco.get("verified"):
        return
    expected_correlations = {
        item["stream"]: item
        for item in payload.get("expected_correlations", [])
    }
    falco_expected = expected_correlations.get("falco", {})
    hits = falco.get("hits", [])
    sql = falco.get("sql", "<not-recorded>")
    raise AssertionError(
        f"Falco correlation verification failed for ability {ability_id}:\n"
        f"  expected: Falco event for rule matching ability\n"
        f"  reason: {falco_expected.get('reason', '<missing>')}\n"
        f"  found: {len(hits)} hit(s)\n"
        f"  verified: {falco.get('verified')}\n"
        f"  stream_not_found: {falco.get('stream_not_found', False)}\n"
        f"  correlation.enabled: {correlation.get('enabled')}\n"
        f"  correlation.verified_count: {correlation.get('verified_count', 0)}/{correlation.get('expected_count', 0)}\n"
        f"  raw falco data: {json.dumps(falco, indent=2, default=str)[:2000]}"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ability_id", SAFE_ABILITIES)
def test_safe_abilities_emit_trace_and_expected_correlations(repo_root: Path, ability_id: str) -> None:
    payload = _run_ability(repo_root, ability_id)

    assert payload["exit_code"] == 0, (
        f"Ability {ability_id} exited with code {payload['exit_code']}; "
        f"stderr: {payload.get('stderr', '')[:500]}"
    )
    _assert_trace_verified(payload, ability_id)

    expected = {item["stream"]: item for item in payload["expected_correlations"]}
    if ability_id in {PAYLOAD_ABILITY, DUMP_HISTORY_ABILITY, AVOID_LOGS_ABILITY}:
        assert expected["falco"]["expected"] is True
        _assert_falco_correlation(payload, ability_id)
        falco_logs = payload["correlation"]["streams"]["falco"]
        assert falco_logs["hits"], (
            f"Expected Falco hit for mapped safe ability {ability_id}, "
            f"but got 0 hits. Raw: {json.dumps(falco_logs, default=str)[:1000]}"
        )
    else:
        assert expected == {}
        assert payload["correlation"]["expected_count"] == 0


def test_payload_ability_reports_falco_expectation(repo_root: Path) -> None:
    payload = _run_ability(repo_root, PAYLOAD_ABILITY)

    expected = {item["stream"]: item for item in payload["expected_correlations"]}
    assert expected["falco"]["expected"] is True
    assert "temp execution detection" in expected["falco"]["reason"]


def test_dump_history_ability_reports_falco_expectation(repo_root: Path) -> None:
    payload = _run_ability(repo_root, DUMP_HISTORY_ABILITY)

    expected = {item["stream"]: item for item in payload["expected_correlations"]}
    assert expected["falco"]["expected"] is True
    assert "bash history access" in expected["falco"]["reason"]


def test_avoid_logs_ability_reports_falco_and_osquery_coverage(repo_root: Path) -> None:
    payload = _run_ability(repo_root, AVOID_LOGS_ABILITY)

    expected = {item["stream"]: item for item in payload["expected_correlations"]}
    assert expected["falco"]["expected"] is True
    assert payload["osquery"]["config"]["bash_profiles"], (
        f"Expected osquery bash_profiles to be configured, got: "
        f"{payload['osquery']['config']['bash_profiles']}"
    )
    assert payload["osquery"]["live_query"]["verified"] is True, (
        f"osquery live query not verified for AVOID_LOGS_ABILITY. "
        f"stdout: {payload['osquery']['live_query'].get('stdout', '')[:500]}, "
        f"stderr: {payload['osquery']['live_query'].get('stderr', '')[:500]}"
    )


def test_detection_coverage_percentage_meets_trace_and_log_baseline(repo_root: Path) -> None:
    results = [_run_ability(repo_root, ability_id) for ability_id in SAFE_ABILITIES]
    report = build_coverage_report(results)
    artifact_path = write_coverage_report(report)

    assert artifact_path.exists()
    assert report["safe_ability_count"] == len(SAFE_ABILITIES)

    trace_pct = report["categories"]["trace"]["coverage_percent"]
    config_pct = report["categories"]["config"]["coverage_percent"]
    overall_pct = report["coverage_percent"]

    assert trace_pct >= 100.0, (
        f"Trace coverage {trace_pct:.1f}% below 100% threshold. "
        f"Details: {json.dumps(report['categories']['trace'], indent=2)}"
    )
    assert config_pct >= 100.0, (
        f"Config coverage {config_pct:.1f}% below 100% threshold. "
        f"Details: {json.dumps(report['categories']['config'], indent=2)}"
    )
    assert overall_pct >= 100.0, (
        f"Overall coverage {overall_pct:.1f}% below 100% threshold. "
        f"({report['total_verified_signals']}/{report['total_expected_signals']}) "
        f"Category breakdown: {json.dumps(report['categories'], indent=2)}"
    )


def test_telemetry_stream_schema_fields_are_populated(repo_root: Path) -> None:
    """Validate that telemetry streams have the expected schema fields populated
    when running under active container workloads.

    This catches situations where OpenObserve has indexed events but is missing
    key fields used by the correlation queries, which would cause false negatives
    in the detection coverage tests.
    """
    # Run just the PAYLOAD_ABILITY which exercises the richest set of streams
    payload = _run_ability(repo_root, PAYLOAD_ABILITY)

    # Validate trace stream schema
    trace_hits = payload.get("trace", {}).get("hits", [])
    missing_trace = validate_stream_schema(
        "default", trace_hits, REQUIRED_STREAM_SCHEMA_FIELDS["default"]
    )
    assert not missing_trace, (
        f"Trace stream missing expected schema fields: {missing_trace}. "
        f"First hit keys: {list(trace_hits[0].keys()) if trace_hits else 'no hits'}"
    )

    # Validate falco stream schema if correlation data is present
    falco_hits = (
        payload.get("correlation", {})
        .get("streams", {})
        .get("falco", {})
        .get("hits", [])
    )
    if falco_hits:
        missing_falco = validate_stream_schema(
            "falco", falco_hits, REQUIRED_STREAM_SCHEMA_FIELDS["falco"]
        )
        assert not missing_falco, (
            f"Falco stream missing expected schema fields: {missing_falco}. "
            f"First hit keys: {list(falco_hits[0].keys()) if falco_hits else 'no hits'}"
        )
