#!/usr/bin/env python3
"""
Generate a combined maturity report JSON and markdown from matrix and optional caldera coverage.
Usage:
  python3 scripts/gen_maturity_report.py --matrix .artifacts/matrix.json --caldera .data/coverage/caldera_detection_coverage.json --out .artifacts/maturity-report.json --md docs/reports/maturity-report.md
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", required=False, default=".artifacts/matrix.json")
    parser.add_argument("--caldera", required=False, default=".data/coverage/caldera_detection_coverage.json")
    parser.add_argument("--out", required=False, default=".artifacts/maturity-report.json")
    parser.add_argument("--md", required=False, default="docs/reports/maturity-report.md")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    matrix_path = root / args.matrix
    caldera_path = root / args.caldera
    out_path = root / args.out
    md_path = root / args.md
    md_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    report = {}

    # Load matrix
    if matrix_path.exists():
        try:
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        except Exception:
            matrix = None
    else:
        matrix = None

    report['matrix_rows'] = matrix if matrix is not None else []
    report['matrix_count'] = len(report['matrix_rows'])

    # Compute per-dimension scores
    DIMENSIONS = [
        'Strategy & Governance',
        'People & Skills',
        'Tooling & Infrastructure',
        'Data & Knowledge Management',
        'Evaluation & QA',
        'Security, Privacy & Safety',
        'Detection Opportunity Ideation',
        'Detection Authoring',
        'Detection Testing & Validation',
        'Tuning, Coverage & Continuous Improvement',
    ]
    dim_scores = {}
    rows = report['matrix_rows']
    if isinstance(rows, list):
        for dim in DIMENSIONS:
            scores = [r.get('score', 0) for r in rows if isinstance(r, dict) and r.get('dimension') == dim]
            dim_scores[dim] = sum(scores) / len(scores) if scores else 0
    report['dimensions'] = dim_scores
    all_vals = list(dim_scores.values())
    report['overall_score'] = sum(all_vals) / len(all_vals) if all_vals else 0
    report['generated_at'] = datetime.now(timezone.utc).isoformat()

    # Load caldera coverage if present
    caldera = None
    if caldera_path.exists():
        try:
            caldera = json.loads(caldera_path.read_text(encoding='utf-8'))
        except Exception:
            caldera = None

    if caldera is not None:
        report['coverage_percent'] = caldera.get('coverage_percent')
        report['safe_ability_count'] = caldera.get('safe_ability_count')
        report['total_expected_signals'] = caldera.get('total_expected_signals')
        report['total_verified_signals'] = caldera.get('total_verified_signals')
        report['coverage_categories'] = caldera.get('categories')
        report['caldera_raw'] = caldera
    else:
        report['coverage_percent'] = None
        report['safe_ability_count'] = 0
        report['total_expected_signals'] = 0
        report['total_verified_signals'] = 0
        report['coverage_categories'] = {}
        report['caldera_raw'] = None

    # Simple totals
    if report['total_expected_signals']:
        report['overall_coverage_pct'] = (
            report['total_verified_signals'] / report['total_expected_signals'] * 100.0
        )
    else:
        report['overall_coverage_pct'] = None

    # Write JSON
    out_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('wrote', out_path)

    # Write markdown summary
    lines = []
    lines.append('# Maturity Report')
    lines.append('')
    lines.append(f'- matrix rows: {report["matrix_count"]}')
    lines.append(f'- overall_score: {report["overall_score"]}')
    if report['coverage_percent'] is not None:
        lines.append(f'- caldera coverage_percent: {report["coverage_percent"]}%')
        lines.append(f'- safe_ability_count: {report["safe_ability_count"]}')
        lines.append(f'- total_expected_signals: {report["total_expected_signals"]}')
        lines.append(f'- total_verified_signals: {report["total_verified_signals"]}')
        lines.append(f'- overall_coverage_pct (computed): {report["overall_coverage_pct"]}%')
        lines.append('')
        lines.append('## Coverage by category')
        for cat, info in (report['coverage_categories'] or {}).items():
            cp = info.get('coverage_percent')
            exp = info.get('expected')
            ver = info.get('verified')
            lines.append(f'- {cat}: {cp}% ({ver}/{exp})')
    else:
        lines.append('- caldera coverage: MISSING')

    md_path.write_text('\n'.join(lines), encoding='utf-8')
    print('wrote', md_path)
    return report


if __name__ == '__main__':
    main()
