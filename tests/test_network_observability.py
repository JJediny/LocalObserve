"""Static safety and compatibility checks for the network observability evaluation."""
from __future__ import annotations

import struct
from pathlib import Path

import yaml

from tools.netflow_probe import netflow_v5_packet


def test_netflow_probe_is_well_formed() -> None:
    packet = netflow_v5_packet(sequence=7, now=1_700_000_000)
    assert len(packet) == 72  # 24-byte v5 header + one 48-byte record
    version, count, _uptime, _seconds, _nanos, sequence, *_rest = struct.unpack(
        "!HHIIIIBBH", packet[:24]
    )
    assert (version, count, sequence) == (5, 1, 7)


def test_snitch_is_an_opt_in_distroless_image(repo_root: Path) -> None:
    dockerfile = (repo_root / "images" / "snitch" / "Dockerfile").read_text()
    assert "CGO_ENABLED=0" in dockerfile
    assert "gcr.io/distroless/static-debian12:nonroot" in dockerfile
    assert "SNITCH_VERSION=v0.2.2" in dockerfile

    compose = yaml.safe_load((repo_root / "docker-compose.yaml").read_text())
    snitch = compose["services"]["snitch"]
    assert snitch["profiles"] == ["network-inspect"]
    assert snitch["build"]["context"] == "./images/snitch"
    assert snitch["read_only"] is True
    assert snitch["network_mode"] == "host"
    assert snitch["pid"] == "host"
    assert snitch["cap_add"] == ["SYS_PTRACE"]
    assert "privileged" not in snitch
    assert snitch["logging"]["options"]["max-file"] == "3"


def test_benchmark_harness_measures_candidate_docker_logs(repo_root: Path) -> None:
    harness = (repo_root / 'tools' / 'bench_stack.py').read_text()
    comparer = (repo_root / 'tools' / 'bench_compare.py').read_text()
    assert 'def docker_log_bytes_mib' in harness
    assert '"docker_log_mib_window"' in harness
    assert 'Docker Logs (MiB/min)' in harness
    assert 'Docker log rate (MiB/min)' in comparer


def test_network_benchmark_orchestrator_is_static(repo_root: Path) -> None:
    import subprocess

    script = repo_root / 'scripts' / 'bench-network.sh'
    assert script.exists()
    result = subprocess.run(['bash', '-n', str(script)], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr

    taskfile = (repo_root / 'Taskfile.yml').read_text()
    assert 'bash scripts/bench-network.sh' in taskfile


def test_evaluation_keeps_opensnitch_off_the_runtime_stack(repo_root: Path) -> None:
    compose = yaml.safe_load((repo_root / "docker-compose.yaml").read_text())
    assert "opensnitch" not in compose["services"]

    evaluation = (repo_root / "docs" / "network_observability_benchmark.md").read_text()
    for project in ("GoFlow2", "Snitch", "OpenSnitch"):
        assert project in evaluation
    assert "disposable Linux VM" in evaluation
    assert "not a drop-in replacement" in evaluation
