from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.caldera_coverage_support import PAYLOAD_ABILITY
from tests.caldera_coverage_support import SAFE_ABILITIES
from tests.caldera_coverage_support import AVOID_LOGS_ABILITY
from tests.caldera_coverage_support import DUMP_HISTORY_ABILITY
from tests.caldera_coverage_support import build_coverage_report
from tests.caldera_coverage_support import write_coverage_report


pytestmark = [pytest.mark.integration, pytest.mark.host_emulation]


def _run(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


def _run_ability(repo_root: Path, ability_id: str) -> dict:
    result = _run(
        repo_root,
        [
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
        ],
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("ability_id", SAFE_ABILITIES)
def test_safe_abilities_emit_trace_and_expected_correlations(repo_root: Path, ability_id: str) -> None:
    payload = _run_ability(repo_root, ability_id)

    assert payload["exit_code"] == 0
    assert payload["trace"]["verified"] is True

    expected = {item["stream"]: item for item in payload["expected_correlations"]}
    if ability_id in {PAYLOAD_ABILITY, DUMP_HISTORY_ABILITY, AVOID_LOGS_ABILITY}:
        assert expected["falco"]["expected"] is True
        falco_logs = payload["correlation"]["streams"]["falco"]
        assert falco_logs["verified"] is True
        assert falco_logs["hits"], "expected Falco hit for mapped safe ability"
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
    assert payload["osquery"]["config"]["bash_profiles"]
    assert payload["osquery"]["live_query"]["verified"] is True


def test_detection_coverage_percentage_meets_trace_and_log_baseline(repo_root: Path) -> None:
    results = [_run_ability(repo_root, ability_id) for ability_id in SAFE_ABILITIES]
    report = build_coverage_report(results)
    artifact_path = write_coverage_report(report)

    assert artifact_path.exists()
    assert report["safe_ability_count"] == len(SAFE_ABILITIES)
    assert report["categories"]["trace"]["coverage_percent"] >= 100.0
    assert report["categories"]["config"]["coverage_percent"] >= 100.0
    assert report["coverage_percent"] >= 100.0, (
        f"expected 100% verified configured/live coverage, got {report['coverage_percent']:.1f}% "
        f"({report['total_verified_signals']}/{report['total_expected_signals']})"
    )
