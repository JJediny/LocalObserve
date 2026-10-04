from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

ALLOWED_PRIORITIES = {
    "EMERGENCY",
    "ALERT",
    "CRITICAL",
    "ERROR",
    "WARNING",
    "NOTICE",
    "INFORMATIONAL",
    "DEBUG",
}


def test_falco_config_loads_as_mapping(falco_config: dict) -> None:
    assert isinstance(falco_config, dict)
    assert falco_config


def test_falco_config_uses_expected_rule_sources(falco_config: dict) -> None:
    rules_files = falco_config["rules_files"]

    assert "/etc/falco/falco_rules.yaml" in rules_files
    assert "/etc/falco/falco_rules.local.yaml" in rules_files
    assert "/etc/falco/rules.d" in rules_files


def test_falco_config_keeps_local_runtime_defaults(falco_config: dict) -> None:
    assert falco_config["engine"]["kind"] == "modern_ebpf"
    assert falco_config["priority"].upper() in ALLOWED_PRIORITIES
    assert falco_config["priority"].lower() == "warning"
    assert falco_config["buffered_outputs"] is True
    assert falco_config["json_output"] is True
    assert falco_config["log_stderr"] is True
    assert falco_config["log_syslog"] is False


def test_falco_config_writes_and_forwards_events(falco_config: dict) -> None:
    """Falco must write events to exactly one sink: the JSONL file the OTel
    collector tails. stdout_output stays off — enabling both would duplicate
    every event into Docker's json-file log driver (SSD wear, see
    docs/benchmark_and_agent_observability_plan.md Part A)."""
    file_output = falco_config["file_output"]
    stdout_output = falco_config["stdout_output"]

    assert file_output["enabled"] is True
    assert file_output["filename"] == "/var/log/falco/events.jsonl"
    assert stdout_output["enabled"] is False

    # http_output is optional — commented out when falcosidekick is not deployed.
    # When present, it must point to falcosidekick:2801.
    if "http_output" in falco_config:
        assert falco_config["http_output"]["enabled"] is True
        assert falco_config["http_output"]["url"] == "http://falcosidekick:2801"


def test_falco_config_disables_unused_syslog_output(falco_config: dict) -> None:
    assert falco_config["syslog_output"]["enabled"] is False


@pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="docker not available; skip binary rule validation",
)
def test_falco_custom_rules_validate_with_docker() -> None:
    """Run falco --list rules in Docker to validate our custom rules parse.

    Uses the same falco version as docker-compose (0.45.0). The falco binary
    prints rule names to stdout and deprecation warnings to stderr; we only
    require exit code 0 (no parse errors).
    """
    rules_file = REPO_ROOT / "rules" / "persistence_techniques.yaml"
    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{rules_file}:/rules/custom.yaml:ro",
            "--entrypoint", "/usr/bin/falco",
            "falcosecurity/falco:0.45.0",
            "-r", "/rules/custom.yaml",
            "--list", "rules",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    # stderr may contain deprecation warnings (k8s.* fields); these are
    # expected when running outside a k8s environment.
    assert result.returncode == 0, (
        f"Falco rule validation failed (exit {result.returncode}):\n"
        f"stderr: {result.stderr[:500]}"
    )


def test_falco_install_system_script_configures_umask_and_output() -> None:
    """scripts/install-falco-system.sh must configure UMask=0022 and JSON output."""
    script_path = REPO_ROOT / "scripts" / "install-falco-system.sh"
    content = script_path.read_text(encoding="utf-8")

    assert "UMask=0022" in content
    assert "localobserve-umask.conf" in content
    assert "json_output: true" in content
    assert "0.45.0" in content
