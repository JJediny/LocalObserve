#!/usr/bin/env python3
"""
parse_scanner_results.py — summarize container image/registry scan JSON.

Reads a Grype (or Trivy-compatible) vulnerability scan JSON file and prints a
concise severity breakdown plus the top findings. Used to triage the results
written by the `scanner` compose service (see docker-compose.yaml `scan` profile)
before they are shipped to OpenObserve.

Usage:
    uv run python tools/parse_scanner_results.py .data/scanner/scan.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

SEVERITY_ORDER = ["critical", "high", "medium", "low", "negligible", "unknown"]


def summarize(scan: dict) -> dict:
    """Return a severity histogram and sorted top findings from a scan doc."""
    matches = scan.get("matches") or []
    by_sev: Counter[str] = Counter()
    findings = []
    for m in matches:
        vuln = m.get("vulnerability", {})
        sev = (vuln.get("severity") or "unknown").lower()
        by_sev[sev] += 1
        artifact = m.get("artifact", {})
        findings.append(
            {
                "id": vuln.get("id"),
                "severity": sev,
                "package": artifact.get("name"),
                "version": artifact.get("version"),
                "fixed": vuln.get("fix", {}).get("state")
                if isinstance(vuln.get("fix"), dict)
                else vuln.get("fix"),
            }
        )
    findings.sort(key=lambda f: (SEVERITY_ORDER.index(f["severity"]), f["id"] or ""))
    return {"total": len(matches), "by_severity": dict(by_sev), "findings": findings}


def render(summary: dict) -> str:
    lines = [f"Total vulnerabilities: {summary['total']}"]
    if summary["by_severity"]:
        lines.append("By severity:")
        for sev in SEVERITY_ORDER:
            if sev in summary["by_severity"]:
                lines.append(f"  {sev:>10}: {summary['by_severity'][sev]}")
    else:
        lines.append("No vulnerabilities found.")
    return "\n".join(lines)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scan_file", help="Path to Grype/Trivy JSON output.")
    args = parser.parse_args(argv)

    path = Path(args.scan_file)
    if not path.exists():
        print(f"error: {path} not found", file=sys.stderr)
        return 1
    try:
        scan = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON in {path}: {exc}", file=sys.stderr)
        return 1

    summary = summarize(scan)
    print(render(summary))
    # Non-zero exit when any critical/high finding exists, for CI gating.
    if summary["by_severity"].get("critical", 0) or summary["by_severity"].get(
        "high", 0
    ):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(run())
