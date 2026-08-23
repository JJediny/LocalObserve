"""Hermetic contract tests for the cross-runtime acceptance entry points.

These tests do not start containers. They verify the runtime adapter, task
wiring, and documented separation between mise-installed clients and host
container engines. Live boot and detection checks remain the responsibility of
``task verify-runtimes`` on an engine-equipped host.
"""
from __future__ import annotations

import os
import shlex
import stat
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_HELPER = REPO_ROOT / "scripts" / "runtime-compose.sh"
RUNTIME_HARNESS = REPO_ROOT / "scripts" / "verify-runtimes.sh"
TRIGGER_SCRIPT = REPO_ROOT / "tools" / "trigger-detections.sh"


def _bash(source: str, *, path: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if path is not None:
        env["PATH"] = str(path)
    return subprocess.run(
        ["/bin/bash", "-c", source],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_runtime_adapter_supports_podman_remote_fallback(tmp_path: Path) -> None:
    remote = tmp_path / "podman-remote"
    _executable(remote, "#!/bin/sh\n")

    result = _bash(
        f"source {shlex.quote(str(RUNTIME_HELPER))}; runtime_binary podman",
        path=tmp_path,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == str(remote)


def test_runtime_compose_adds_isolated_project_without_shell_reparsing(
    tmp_path: Path,
) -> None:
    docker = tmp_path / "docker"
    _executable(docker, "#!/bin/sh\nprintf '%s\\n' \"$@\"\n")

    result = _bash(
        "source "
        f"{shlex.quote(str(RUNTIME_HELPER))}; "
        "COMPOSE_PROJECT_NAME=acceptance-unit runtime_compose docker config",
        path=tmp_path,
    )

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["compose", "-p", "acceptance-unit", "config"]


def test_runtime_scripts_are_valid_bash() -> None:
    for script in (RUNTIME_HELPER, RUNTIME_HARNESS, TRIGGER_SCRIPT):
        result = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{script}: {result.stderr}"


def test_harness_preflights_engines_and_cleans_partial_stacks() -> None:
    harness = RUNTIME_HARNESS.read_text()
    assert "runtime_engine_available" in harness
    assert "engine is unavailable" in harness
    assert "REQUIRED_TCP_PORTS" in harness
    assert "host_ports_available" in harness
    assert "started=1" in harness
    assert "trap cleanup EXIT INT TERM" in harness
    assert "RUNTIME=\"$rt\" COMPOSE_PROJECT_NAME=\"$project\"" in harness
    assert "tools/trigger-detections.sh" in harness


def test_detection_trigger_uses_selected_runtime() -> None:
    trigger = TRIGGER_SCRIPT.read_text()
    assert "runtime_compose \"$RUNTIME\"" in trigger
    assert "ALERT_RECEIVER_URL" in trigger
    assert "docker ps --format" not in trigger


def test_scan_tasks_use_the_runtime_parameter() -> None:
    taskfile = yaml.safe_load((REPO_ROOT / "Taskfile.yml").read_text())
    for task_name in ("scan-image", "scan-registry"):
        task = taskfile["tasks"][task_name]
        assert "RUNTIME" in task["vars"]
        commands = " ".join(task["cmds"])
        assert "{{.RUNTIME}} compose" in commands


def test_secret_scan_is_invoked_through_mise() -> None:
    taskfile = yaml.safe_load((REPO_ROOT / "Taskfile.yml").read_text())
    commands = " ".join(taskfile["tasks"]["secret-scan"]["cmds"])
    assert "mise exec betterleaks -- betterleaks dir" in commands


def test_testing_plan_describes_the_active_pipeline() -> None:
    plan = (REPO_ROOT / "docs" / "testing-plan.md").read_text()
    assert "OpenObserve" in plan
    assert "OTel Collector" in plan
    assert "task verify-runtimes" in plan
    assert "loki-write" not in plan
    assert "alloy-local-config.yaml" not in plan
