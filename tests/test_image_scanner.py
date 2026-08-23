"""Tests for Issue #57 — container image/registry scanner integration.

Validates the compose `scanner` service definition and exercises the
results parser against a sample Grype-style JSON document (offline).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "parse_scanner_results", REPO_ROOT / "tools" / "parse_scanner_results.py"
)
parser = importlib.util.module_from_spec(_spec)
sys.modules["parse_scanner_results"] = parser
_spec.loader.exec_module(parser)

SAMPLE_SCAN = {
    "matches": [
        {
            "vulnerability": {"id": "CVE-2020-1234", "severity": "Critical", "fix": {"state": "fixed"}},
            "artifact": {"name": "openssl", "version": "1.1.1"},
        },
        {
            "vulnerability": {"id": "CVE-2021-5678", "severity": "High", "fix": {"state": "not-fixed"}},
            "artifact": {"name": "bash", "version": "5.0"},
        },
        {
            "vulnerability": {"id": "CVE-2022-9999", "severity": "Low", "fix": "fixed-version"},
            "artifact": {"name": "coreutils", "version": "8.30"},
        },
    ]
}


def test_scanner_service_defined_under_scan_profile():
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yaml").read_text())
    assert "scanner" in compose["services"]
    svc = compose["services"]["scanner"]
    assert "scan" in (svc.get("profiles") or [])
    # Writes results into the shared volume the parser consumes.
    assert any("/var/lib/scanner" in v for v in svc.get("volumes", []))
    # Results path referenced by the parser/CI tasks (./ prefix is equivalent).
    assert any(v.endswith(".data/scanner:/var/lib/scanner:z") for v in svc.get("volumes", []))


def test_parser_summarizes_by_severity():
    summary = parser.summarize(SAMPLE_SCAN)
    assert summary["total"] == 3
    assert summary["by_severity"]["critical"] == 1
    assert summary["by_severity"]["high"] == 1
    assert summary["by_severity"]["low"] == 1
    # Sorted most-severe first.
    assert summary["findings"][0]["id"] == "CVE-2020-1234"


def test_parser_returns_nonzero_on_critical_for_ci_gating(tmp_path):
    doc = tmp_path / "scan.json"
    doc.write_text(json.dumps(SAMPLE_SCAN))
    assert parser.run([str(doc)]) == 2  # critical/high present => gate fails


def test_parser_clean_when_no_findings(tmp_path):
    doc = tmp_path / "scan.json"
    doc.write_text(json.dumps({"matches": []}))
    assert parser.run([str(doc)]) == 0
