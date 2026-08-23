"""Tests for Issue #50 — OTTL-based log volume reduction in the OTEL collector.

Validates that the `filter`/`transform` processors exist, are correctly defined
with OTTL expressions, and are wired into the active log pipelines. A deeper
check runs `otelcol --config` validation when the binary is available.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

# Pipelines that should carry the reduction processors.
TARGET_PIPELINES = ["logs/osquery", "logs/falco", "logs/otlp"]


@pytest.fixture(scope="session")
def collector_config():
    return yaml.safe_load((REPO_ROOT / "otel-collector-config.yaml").read_text())


def test_ottl_processors_are_defined(collector_config):
    procs = collector_config["processors"]
    assert "filter/drop_osquery_status" in procs
    assert "transform/redact_large_payloads" in procs


def test_filter_expr_targets_low_priority_logs(collector_config):
    flt = collector_config["processors"]["filter/drop_osquery_status"]
    assert flt.get("error_mode") == "ignore"
    # Only drops osquery daemon "status" chatter; never security detections.
    assert any(
        'body["log_type"] == "status"' in rule.get("expr", "")
        for rule in flt.get("logs", [])
    )


def test_transform_caps_oversized_payloads(collector_config):
    tr = collector_config["processors"]["transform/redact_large_payloads"]
    statements = tr["log_statements"][0]
    assert "Len(body) > 8192" in statements["conditions"][0]
    assert any("set(body" in s for s in statements["statements"])


def test_processors_wired_into_pipelines(collector_config):
    pipelines = collector_config["service"]["pipelines"]
    for name in TARGET_PIPELINES:
        procs = pipelines[name]["processors"]
        assert "filter/drop_osquery_status" in procs
        assert "transform/redact_large_payloads" in procs
        # Reduction must run before fields are flattened away (where applicable).
        if "transform/flatten" in procs:
            assert procs.index("filter/drop_osquery_status") < procs.index(
                "transform/flatten"
            )


@pytest.mark.skipif(
    shutil.which("otelcol") is None and shutil.which("otelcol-contrib") is None,
    reason="otelcol binary not installed; structural validation only",
)
def test_collector_config_validates_with_binary(collector_config, tmp_path):
    binary = shutil.which("otelcol") or shutil.which("otelcol-contrib")
    # Render to a temp file so the real parser validates OTTL syntax.
    cfg = tmp_path / "otel-collector-config.yaml"
    cfg.write_text((REPO_ROOT / "otel-collector-config.yaml").read_text())
    result = subprocess.run(
        [binary, "--config", str(cfg), "validate"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
