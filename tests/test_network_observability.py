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


def test_netflow_probe_counts_unique_rotated_sequences(tmp_path: Path) -> None:
    import gzip
    import json

    from tools.count_netflow_probe import count_sequences

    def probe_line(sequence: int) -> str:
        return json.dumps({
            'Type': 'NETFLOW_V5',
            'SrcAddr': '192.0.2.10',
            'DstAddr': '198.51.100.20',
            'SequenceNum': sequence,
        })

    (tmp_path / 'flows.jsonl.1').write_text(probe_line(1) + '\n')
    with gzip.open(tmp_path / 'flows.jsonl.2.gz', 'wt') as handle:
        handle.write(probe_line(2) + '\n')
    (tmp_path / 'flows.jsonl').write_text(probe_line(3) + '\n')
    assert count_sequences(tmp_path, start=1, end=3) == 3
    assert count_sequences(tmp_path, start=2, end=3) == 2


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


def test_network_report_aggregates_repeated_phase_artifacts(tmp_path: Path) -> None:
    from tools.bench_network_report import load_groups, render_report

    def summary(service: str, ram: float, cpu: float, log: float = 0.0) -> dict:
        return {
            'budget_ok': True,
            'per_service': {service: {'ram_max_mib': ram, 'cpu_max_pct': cpu}},
            'io_write_mib_window': {},
            'docker_log_mib_window': {service: log},
        }

    for repeat, values in ((1, (10, 20)), (2, (12, 24))):
        (tmp_path / f'rep{repeat}-baseline-a').mkdir()
        (tmp_path / f'rep{repeat}-goflow-b').mkdir()
        (tmp_path / f'rep{repeat}-baseline-a' / 'summary.json').write_text(
            __import__('json').dumps(summary('openobserve', 100, 5))
        )
        (tmp_path / f'rep{repeat}-goflow-b' / 'summary.json').write_text(
            __import__('json').dumps(summary('goflow2', values[0], values[1]))
        )

    report = render_report(load_groups(tmp_path))
    assert 'Goflow2 vs. core baseline' in report
    assert '11.0' in report
    assert '22.0' in report


def test_evaluation_keeps_opensnitch_off_the_runtime_stack(repo_root: Path) -> None:
    compose = yaml.safe_load((repo_root / "docker-compose.yaml").read_text())
    assert "opensnitch" not in compose["services"]

    evaluation = (repo_root / "docs" / "network_observability_benchmark.md").read_text()
    for project in ("GoFlow2", "Snitch", "OpenSnitch"):
        assert project in evaluation
    assert "disposable Linux VM" in evaluation
    assert "not a drop-in replacement" in evaluation
