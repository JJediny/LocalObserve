"""Contract tests for the mise-managed OSV-Scanner source scan."""
from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_osv_scanner_is_pinned_in_mise() -> None:
    with (REPO_ROOT / "mise.toml").open("rb") as handle:
        tools = tomllib.load(handle)["tools"]
    assert tools["osv-scanner"] == "2.5.1"


def test_scan_osv_task_is_mise_managed_and_offline_capable() -> None:
    taskfile = yaml.safe_load((REPO_ROOT / "Taskfile.yml").read_text())
    task = taskfile["tasks"]["scan-osv"]
    assert task["vars"]["TARGET"] == '{{.TARGET | default "."}}'
    assert task["vars"]["OFFLINE"] == '{{.OFFLINE | default "false"}}'
    commands = " ".join(task["cmds"])
    assert "mise exec osv-scanner -- osv-scanner scan source" in commands
    assert "--recursive" in commands
    assert "--format json" in commands
    assert "--output-file .data/scanner/osv-scan.json" in commands
    assert "--offline" in commands


def test_osv_scanner_binary_reports_pinned_version_when_installed() -> None:
    binary = shutil.which("osv-scanner")
    if binary is None:
        candidate = (
            REPO_ROOT.parent
            / ".local/share/mise/installs/osv-scanner/2.5.1/osv-scanner"
        )
        binary = str(candidate) if candidate.exists() else None
    if binary is None:
        pytest.skip("osv-scanner binary not available")

    result = subprocess.run(
        [binary, "--version"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "2.5.1" in result.stdout
