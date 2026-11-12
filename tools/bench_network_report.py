#!/usr/bin/env python3
"""Aggregate repeated network benchmark artifacts into median Markdown results."""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS = REPO_ROOT / ".artifacts" / "bench" / "network-eval"
CANDIDATE_PHASES = {'goflow2': 'goflow', 'snitch': 'snitch'}
RUN_PATTERN = re.compile(r'^rep(\d+)-(baseline|goflow|snitch)-')


def load_groups(runs_dir: Path) -> dict[tuple[int, str], list[dict]]:
    groups: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for run_dir in sorted(runs_dir.iterdir()):
        match = RUN_PATTERN.match(run_dir.name)
        summary_path = run_dir / "summary.json"
        if not match or not run_dir.is_dir() or not summary_path.exists():
            continue
        groups[(int(match.group(1)), match.group(2))].append(
            json.loads(summary_path.read_text())
        )
    return groups


def _service_metric(summary: dict, service: str, field: str) -> float:
    if field == "write":
        return float(summary.get("io_write_mib_window", {}).get(service, 0.0))
    if field == "log":
        return float(summary.get("docker_log_mib_window", {}).get(service, 0.0))
    return float(summary.get("per_service", {}).get(service, {}).get(field, 0.0))


def _median(values: list[float]) -> float:
    return round(statistics.median(values), 3) if values else 0.0


def summarize_phase(
    summaries: list[dict],
    services: list[str],
) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for service in services:
        result[service] = {
            "ram": _median([_service_metric(s, service, "ram_max_mib") for s in summaries]),
            "cpu": _median([_service_metric(s, service, "cpu_max_pct") for s in summaries]),
            "write": _median([_service_metric(s, service, "write") for s in summaries]),
            "log": _median([_service_metric(s, service, "log") for s in summaries]),
        }
    return result


def render_report(groups: dict[tuple[int, str], list[dict]]) -> str:
    repeats = sorted({repeat for repeat, _ in groups})
    lines = ["# Network observability benchmark aggregate", ""]
    lines.append(f"- Repeats with at least one artifact: {len(repeats)}")

    all_budgets_ok = all(
        bool(summary.get("budget_ok", False))
        for summaries in groups.values()
        for summary in summaries
    )
    lines.append(f"- All recorded harness phases passed budgets: {all_budgets_ok}")
    lines.append("")

    common_services = [
        "openobserve",
        "otel-collector",
        "alert-receiver",
        "osquery",
        "rsigma",
    ]
    candidate_services = ["goflow2", "snitch"]
    table_services = candidate_services + common_services

    for candidate, candidate_phase in CANDIDATE_PHASES.items():
        baseline_key = 'baseline'
        baseline = [
            summary
            for repeat in repeats
            for summary in groups.get((repeat, baseline_key), [])
        ]
        current = [
            summary
            for repeat in repeats
            for summary in groups.get((repeat, candidate_phase), [])
        ]
        if not baseline or not current:
            lines.append(f"## {candidate.title()}")
            lines.append("")
            lines.append("No completed paired phase artifacts were found yet.")
            lines.append("")
            continue

        base = summarize_phase(baseline, table_services)
        cur = summarize_phase(current, table_services)
        lines.extend(
            [
                f"## {candidate.title()} vs. core baseline (median of maxima/rates)",
                "",
                "| Service | Baseline RAM | Candidate RAM | Baseline CPU | Candidate CPU | Baseline writes | Candidate writes | Baseline logs | Candidate logs |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for service in table_services:
            lines.append(
                f"| {service} | {base[service]['ram']:.1f} | {cur[service]['ram']:.1f} | "
                f"{base[service]['cpu']:.1f} | {cur[service]['cpu']:.1f} | "
                f"{base[service]['write']:.3f} | {cur[service]['write']:.3f} | "
                f"{base[service]['log']:.3f} | {cur[service]['log']:.3f} |"
            )
        lines.append("")

    lines.append("RAM and CPU are medians of each run window's maximum.")
    lines.append("Write and log rates are medians of MiB/min from each run window.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = render_report(load_groups(args.runs))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report)
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
