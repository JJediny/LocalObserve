"""Tests for Issue #58 — secret-scanning integration (betterleaks via mise).

Validates the committed config and that the Taskfile wires `betterleaks dir`.
The deeper check runs Betterleaks' `config check` against the installed binary
when mise has activated it (skipped otherwise).
"""
from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / ".betterleaks.toml"


def test_betterleaks_config_is_valid_toml():
    assert CONFIG.exists()
    with CONFIG.open("rb") as fh:
        cfg = tomllib.load(fh)
    # gitleaks-compatible schema: extends the default ruleset.
    assert cfg.get("extend", {}).get("useDefault") is True


def test_secret_scan_task_uses_betterleaks():
    taskfile = yaml.safe_load((REPO_ROOT / "Taskfile.yml").read_text())
    assert "secret-scan" in taskfile["tasks"]
    body = " ".join(taskfile["tasks"]["secret-scan"]["cmds"])
    assert "betterleaks dir" in body
    assert ".betterleaks.toml" in body


def test_betterleaks_config_validates_with_binary():
    binary = shutil.which("betterleaks")
    if binary is None:
        # Try the mise-managed install path directly.
        candidate = (
            REPO_ROOT.parent
            / ".local/share/mise/installs/betterleaks/1.8.1/betterleaks"
        )
        binary = str(candidate) if candidate.exists() else None
    if binary is None:
        pytest.skip("betterleaks binary not available")
    result = subprocess.run(
        [binary, "config", "check", "--config", str(CONFIG)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
