#!/usr/bin/env python3
"""
Very small heuristic maturity assessment generator.
Scans for a few repo artifacts and writes docs/reports/maturity-assessment.md
"""
import os
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

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'reports'
OUT.mkdir(parents=True, exist_ok=True)

report_lines = []
report_lines.append('# Maturity Assessment\n')

# 1. Artifact: matrix.json
matrix = ROOT / '.artifacts' / 'matrix.json'
if matrix.exists():
    try:
        import json
        rows = json.loads(matrix.read_text())
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
if (ROOT / 'docker-compose.yaml').exists() or (ROOT / 'docker-compose.yml').exists():
    report_lines.append('- docker-compose: present')
else:
    report_lines.append('- docker-compose: missing')

# 3. tests folder
if (ROOT / 'tests').exists():
    count = sum(1 for _ in (ROOT / 'tests').rglob('test_*.py'))
    report_lines.append(f'- tests: {count} test files')
else:
    report_lines.append('- tests: missing')

# 4. python venv
if (ROOT / '.venv').exists() or (ROOT / '.venv.ci').exists():
    report_lines.append('- virtualenvs: detected')
else:
    report_lines.append('- virtualenvs: not detected')

# 5. CI workflows
ci_dir = ROOT / '.github' / 'workflows'
if ci_dir.exists():
    workflows = list(ci_dir.glob('*.yml')) + list(ci_dir.glob('*.yaml'))
    report_lines.append(f'- CI workflows: {len(workflows)}')
else:
    report_lines.append('- CI workflows: none')

# 6. docker images / compose references in repo
has_dockerfile = any(ROOT.rglob('Dockerfile'))
report_lines.append(f'- Dockerfile present: {has_dockerfile}')

# 7. quick heuristic for RAG: presence of "docs/" or "corpus" or "data/"
if (ROOT / 'docs').exists() or any(ROOT.rglob('*.md')):
    report_lines.append('- documentation: present')
else:
    report_lines.append('- documentation: missing')

# Write report
OUT_FILE = OUT / 'maturity-assessment.md'
OUT_FILE.write_text('\n'.join(report_lines))
print('wrote', OUT_FILE)
