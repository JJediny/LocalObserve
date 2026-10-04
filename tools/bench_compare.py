#!/usr/bin/env python3
"""Compare two benchmark runs (latest vs. baseline) and print a delta report.

Usage:
  uv run python tools/bench_compare.py                    # latest vs. previous
  uv run python tools/bench_compare.py <run-a> <run-b>    # explicit run ids
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ARTIFACT_ROOT = Path(__file__).resolve().parents[1] / ".artifacts" / "bench"


def load(run_id: str) -> dict:
    p = ARTIFACT_ROOT / run_id / "summary.json"
    if not p.exists():
        raise SystemExit(f"No summary found for run id '{run_id}' at {p}")
    return json.loads(p.read_text())


def latest_run_ids(n: int = 2) -> list[str]:
    runs = sorted(
        (p.parent.name for p in ARTIFACT_ROOT.glob("*/summary.json")),
    )
    if len(runs) < n:
        raise SystemExit(f"Need at least {n} runs; found: {runs}")
    return runs[-2:]


def fmt_delta(a: float, b: float) -> str:
    if a == 0:
        return f"{b - a:+.2f}"
    pct = (b - a) / a * 100.0
    return f"{b - a:+.2f} ({pct:+.0f}%)"


def main() -> int:
    if len(sys.argv) == 3:
        baseline_id, current_id = sys.argv[1], sys.argv[2]
    else:
        baseline_id, current_id = latest_run_ids()

    baseline, current = load(baseline_id), load(current_id)
    base_svc = baseline["per_service"]
    cur_svc = current["per_service"]

    print(f"Baseline : {baseline_id} ({baseline.get('scenario')})")
    print(f"Current  : {current_id} ({current.get('scenario')})")
    print()
    print("| Service | RAM (MiB) | CPU max % | Write rate (MiB/min) |")
    print("|---|---|---|---|")
    for svc in sorted(set(base_svc) | set(cur_svc)):
        b, c = base_svc.get(svc, {}), cur_svc.get(svc, {})
        bw = baseline.get("io_write_mib_window", {}).get(svc, 0.0)
        cw = current.get("io_write_mib_window", {}).get(svc, 0.0)
        print(
            f"| {svc} "
            f"| {fmt_delta(b.get('ram_max_mib', 0), c.get('ram_max_mib', 0))} "
            f"| {fmt_delta(b.get('cpu_max_pct', 0), c.get('cpu_max_pct', 0))} "
            f"| {fmt_delta(bw, cw)} |"
        )
    print()
    print(f"Baseline budgets ok: {baseline.get('budget_ok')}")
    print(f"Current  budgets ok: {current.get('budget_ok')}")
    for p in current.get("budget_problems", []):
        print(f"  ! {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
