#!/usr/bin/env python3
"""LocalObserve stack resource benchmark harness.

Samples per-service RAM, CPU and SSD I/O of the running compose stack and
writes machine- and human-readable artifacts under .artifacts/bench/<run-id>/.

Scenarios:
  idle   - steady-state sampling (default; used for budget enforcement)
  attack - synthetic detections (event-generator) + detection-latency SLO probe
  agent  - runs tools/agent_session_demo.py and measures marginal cost
  scan   - ClamAV sweep observation (informational; budgets exempt)

Examples:
  uv run python tools/bench_stack.py --scenario idle --duration 300
  uv run python tools/bench_stack.py --scenario agent --duration 120
  uv run python tools/bench_compare.py   # after >= 2 runs
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUDGETS_PATH = REPO_ROOT / "tools" / "bench_budgets.json"
ARTIFACT_ROOT = REPO_ROOT / ".artifacts" / "bench"

# Respect an explicit docker context (e.g. DOCKER_CONTEXT=default when the
# stack runs on the system daemon instead of Docker Desktop).
DOCKER_CONTEXT = ["--context", os.environ["DOCKER_CONTEXT"]] if os.environ.get("DOCKER_CONTEXT") else []

CGROUP_V2_IO = Path("/sys/fs/cgroup")


def sh(cmd: list[str], timeout: float = 30.0) -> str:
    res = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, check=False
    )
    if res.returncode != 0:
        raise RuntimeError(f"command failed ({res.returncode}): {' '.join(cmd)}\n{res.stderr}")
    return res.stdout


def docker_ps_services() -> dict[str, str]:
    """Map compose service name -> container id."""
    out = sh(
        [
            "docker", *DOCKER_CONTEXT, "compose", "ps", "--all", "--format",
            "{{.Service}}\t{{.ID}}",
        ]
    )
    services: dict[str, str] = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        name, cid = line.split("\t", 1)
        services[name] = cid
    return services


def docker_stats() -> dict[str, dict[str, float]]:
    """Parse `docker stats --no-stream` into MiB floats."""
    out = sh(["docker", *DOCKER_CONTEXT, "stats", "--no-stream", "--format",
              "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"])
    stats: dict[str, dict[str, float]] = {}
    for line in out.splitlines():
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) != 3:
            continue
        name, cpu_s, mem_s = parts
        cpu = float(cpu_s.rstrip("%"))
        used, _limit = [to_mib(v) for v in mem_s.split("/")]
        stats[name] = {"cpu_pct": cpu, "ram_mib": used}
    return stats


def to_mib(value: str) -> float:
    value = value.strip()
    m = re.match(r"^([\d.]+)\s*([kKmMgG]?)(?:i?B)?$|^([\d.]+)$", value)
    if not m:
        return 0.0
    if m.group(3):
        return float(m.group(3)) / (1024 * 1024)
    num = float(m.group(1))
    unit = (m.group(2) or "").lower()
    mult = {"k": 1 / 1024, "m": 1.0, "g": 1024.0}.get(unit, 1.0)
    if unit == "k":
        return num / 1024
    if unit == "m":
        return num
    if unit == "g":
        return num * 1024
    return num * mult


def container_io_bytes_mib(cid: str) -> tuple[float, float]:
    """Per-container read/write bytes via cgroup v2 io.stat.

    The compose `ps` output yields short (12-char) container IDs, while cgroup
    scope directories use the full 64-char ID, so match scopes by prefix.
    """
    scope_prefix = f"docker-{cid[:12]}"
    for scope in (CGROUP_V2_IO / "system.slice").glob(f"{scope_prefix}*.scope"):
        io_file = scope / "io.stat"
        if io_file.exists():
            read_b = write_b = 0
            for line in io_file.read_text().splitlines():
                for tok in line.split():
                    if tok.startswith("rbytes="):
                        read_b += int(tok.split("=", 1)[1])
                    elif tok.startswith("wbytes="):
                        write_b += int(tok.split("=", 1)[1])
            return read_b / (1024 * 1024), write_b / (1024 * 1024)
    # Fallback: docker API does not expose io; report zeros.
    return 0.0, 0.0


def dir_size_mib(path: Path) -> float:
    total = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
    except PermissionError:
        pass
    return total / (1024 * 1024)


def sample(services: dict[str, str]) -> list[dict]:
    rows: list[dict] = []
    stats = docker_stats()
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    for name, cid in services.items():
        read_mib, write_mib = container_io_bytes_mib(cid)
        s = (
            stats.get(name)
            or stats.get(f"localobserve-{name}-1")
            or {"cpu_pct": 0.0, "ram_mib": 0.0}
        )
        rows.append(
            {
                "timestamp": ts,
                "service": name,
                "cpu_pct": s["cpu_pct"],
                "ram_mib": round(s["ram_mib"], 2),
                "io_read_mib": round(read_mib, 3),
                "io_write_mib": round(write_mib, 3),
            }
        )
    return rows


def summarize(samples: list[dict], budgets: dict) -> dict:
    by_service: dict[str, dict[str, float]] = {}
    first = {}
    last = {}
    for row in samples:
        svc = row["service"]
        agg = by_service.setdefault(svc, {"ram_max_mib": 0.0, "cpu_max_pct": 0.0})
        agg["ram_max_mib"] = max(agg["ram_max_mib"], row["ram_mib"])
        agg["cpu_max_pct"] = max(agg["cpu_max_pct"], row["cpu_pct"])
        if svc not in first:
            first[svc] = (row["io_read_mib"], row["io_write_mib"])
        last[svc] = (row["io_read_mib"], row["io_write_mib"])

    write_rates = {}
    for svc in by_service:
        if svc in first and svc in last:
            written = last[svc][1] - first[svc][1]
            write_rates[svc] = max(0.0, written)
    return {
        "per_service": by_service,
        "io_write_mib_window": write_rates,
        "budgets": budgets,
    }


def check_budgets(summary: dict, duration_s: float, exempt: set[str]) -> tuple[bool, list[str]]:
    ok = True
    problems: list[str] = []
    budgets = summary["budgets"]
    minutes = max(duration_s / 60.0, 1 / 60.0)
    ram_budgets = budgets.get("ram_mib", {})
    total_ram = 0.0
    for svc, agg in summary["per_service"].items():
        if svc in exempt:
            continue
        total_ram += agg["ram_max_mib"]
        if svc in ram_budgets and agg["ram_max_mib"] > ram_budgets[svc]:
            ok = False
            problems.append(
                f"RAM budget exceeded: {svc} measured {agg['ram_max_mib']:.1f} MiB > "
                f"budget {ram_budgets[svc]} MiB"
            )
    if total_ram > budgets.get("stack_ram_mib_total", float("inf")):
        ok = False
        problems.append(f"Stack total RAM {total_ram:.1f} MiB exceeds budget")
    total_write_rate = 0.0
    write_budgets = budgets.get("write_mib_per_min", {})
    for svc, written in summary["io_write_mib_window"].items():
        if svc in exempt:
            continue
        rate = written / minutes
        total_write_rate += rate
        if svc in write_budgets and rate > write_budgets[svc]:
            ok = False
            problems.append(
                f"Write budget exceeded: {svc} {rate:.2f} MiB/min > "
                f"budget {write_budgets[svc]} MiB/min"
            )
    stack_budget = budgets.get("stack_write_mib_per_min_total", float("inf"))
    if total_write_rate > stack_budget:
        ok = False
        problems.append(
            f"Stack write rate {total_write_rate:.2f} MiB/min exceeds budget {stack_budget}"
        )
    return ok, problems


def render_markdown(run_id: str, duration_s: float, summary: dict, problems: list[str]) -> str:
    lines = [
        f"# Benchmark run `{run_id}`",
        "",
        f"- Duration: {duration_s:.0f}s",
        f"- Generated: {dt.datetime.now(dt.timezone.utc).isoformat()}",
        "",
        "| Service | Max RAM (MiB) | Max CPU % | Writes (MiB) |",
        "|---|---:|---:|---:|",
    ]
    for svc, agg in sorted(summary["per_service"].items()):
        writes = summary["io_write_mib_window"].get(svc, 0.0)
        lines.append(
            f"| {svc} | {agg['ram_max_mib']:.1f} | {agg['cpu_max_pct']:.1f} | {writes:.3f} |"
        )
    lines += ["", "## Budget verdict", ""]
    if problems:
        lines += ["**FAIL**", ""]
        lines += [f"- {p}" for p in problems]
    else:
        lines += ["**PASS** - all budgets satisfied", ""]
    return "\n".join(lines) + "\n"


def run_agent_demo() -> None:
    demo = REPO_ROOT / "tools" / "agent_session_demo.py"
    if demo.exists():
        subprocess.run(
            ["uv", "run", "python", str(demo)],
            cwd=REPO_ROOT,
            check=False,
            timeout=300,
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", choices=["idle", "attack", "agent", "scan"], default="idle")
    ap.add_argument("--duration", type=float, default=300.0, help="seconds")
    ap.add_argument("--interval", type=float, default=10.0, help="seconds between samples")
    args = ap.parse_args()

    budgets = json.loads(BUDGETS_PATH.read_text())
    exempt = set(budgets.get("scan_profile_exempt_services", []))

    services = docker_ps_services()
    if not services:
        print("No running compose services found. Start the stack first: docker compose up -d", file=sys.stderr)
        return 2

    run_id = f"{args.scenario}-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    out_dir = ARTIFACT_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.scenario == "agent":
        run_agent_demo()

    print(f"Benchmarking {len(services)} services for {args.duration:.0f}s (interval {args.interval}s)...")
    samples: list[dict] = []
    started = time.monotonic()
    while time.monotonic() - started < args.duration:
        samples.extend(sample(services))
        time.sleep(args.interval)

    summary = summarize(samples, budgets)
    minutes = args.duration / 60.0
    for svc in summary["io_write_mib_window"]:
        summary["io_write_mib_window"][svc] = round(
            summary["io_write_mib_window"][svc] / minutes, 4
        )

    ok, problems = (
        check_budgets(summary, args.duration, exempt)
        if args.scenario in ("idle", "agent")
        else (True, ["budgets not enforced for scenario: " + args.scenario])
    )

    summary["run_id"] = run_id
    summary["scenario"] = args.scenario
    summary["duration_s"] = args.duration
    summary["budget_ok"] = ok
    summary["budget_problems"] = problems

    with (out_dir / "samples.csv").open("w", newline="") as f:
        if samples:
            w = csv.DictWriter(f, fieldnames=list(samples[0].keys()))
            w.writeheader()
            w.writerows(samples)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out_dir / "summary.md").write_text(render_markdown(run_id, args.duration, summary, problems))

    print(f"\nArtifacts: {out_dir}")
    print(render_markdown(run_id, args.duration, summary, problems))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
