#!/usr/bin/env python3
"""
Very small heuristic maturity assessment generator.
Scans for a few repo artifacts and writes docs/reports/maturity-assessment.md
"""
import os
import json
import argparse
from pathlib import Path

REQUIRED_DIMENSIONS = [
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


def main(argv=None, root_dir=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", required=False, default=".artifacts/matrix.json")
    parser.add_argument("--out-dir", required=False, default="docs/reports")
    args = parser.parse_args(argv)

    root = Path(root_dir) if root_dir else Path(__file__).resolve().parents[1]
    matrix_path = root / args.matrix
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    report_lines = []
    report_lines.append('# Maturity Assessment\n')

    # 1. Artifact: matrix.json
    if matrix_path.exists():
        try:
            rows = json.loads(matrix_path.read_text(encoding="utf-8"))
            report_lines.append(f'- Maturity matrix rows: {len(rows)}')

            # Validate dimensions
            found_dims = set()
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict) and 'dimension' in row:
                        found_dims.add(row['dimension'])
            for dim in REQUIRED_DIMENSIONS:
                if dim not in found_dims:
                    print(f'WARNING: matrix.json missing dimension: {dim}')
                else:
                    report_lines.append(f'- Dimension present: {dim}')
        except Exception:
            report_lines.append('- Maturity matrix: present but unreadable')
    else:
        report_lines.append('- Maturity matrix: MISSING')

    # 2. docker-compose
    if (root / 'docker-compose.yaml').exists() or (root / 'docker-compose.yml').exists():
        report_lines.append('- docker-compose: present')
    else:
        report_lines.append('- docker-compose: missing')

    # 3. tests folder
    if (root / 'tests').exists():
        count = sum(1 for _ in (root / 'tests').rglob('test_*.py'))
        report_lines.append(f'- tests: {count} test files')
    else:
        report_lines.append('- tests: missing')

    # 4. python venv
    if (root / '.venv').exists() or (root / '.venv.ci').exists():
        report_lines.append('- virtualenvs: detected')
    else:
        report_lines.append('- virtualenvs: not detected')

    # 5. CI workflows
    ci_dir = root / '.github' / 'workflows'
    if ci_dir.exists():
        workflows = list(ci_dir.glob('*.yml')) + list(ci_dir.glob('*.yaml'))
        report_lines.append(f'- CI workflows: {len(workflows)}')
    else:
        report_lines.append('- CI workflows: none')

    # 6. docker images / compose references in repo
    has_dockerfile = any(root.rglob('Dockerfile'))
    report_lines.append(f'- Dockerfile present: {has_dockerfile}')

    # 7. quick heuristic for RAG: presence of "docs/" or "corpus" or "data/"
    if (root / 'docs').exists() or any(root.rglob('*.md')):
        report_lines.append('- documentation: present')
    else:
        report_lines.append('- documentation: missing')

    # Write report
    out_file = out_dir / 'maturity-assessment.md'
    out_file.write_text('\n'.join(report_lines), encoding='utf-8')
    print('wrote', out_file)
    return report_lines


if __name__ == '__main__':
    main()
