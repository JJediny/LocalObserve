#!/usr/bin/env bash
set -euo pipefail

# Ensure submodules are initialized
git submodule update --init --recursive

FRAMEWORK_DIR=tools/detection-engineering-ai-maturity
cd "$FRAMEWORK_DIR"

# Build site
if command -v npm >/dev/null 2>&1; then
  npm ci
  npm run build
else
  echo "npm not available; skipping site build"
fi

# Extract matrix CSV to JSON (simple conversion)
MATRIX_CSV=public/assets/matrix.csv
MATRIX_JSON=../../.artifacts/matrix.json
mkdir -p ../../.artifacts
python3 - <<'PY'
import csv, json, sys
from pathlib import Path
p=Path('public/assets/matrix.csv')
if not p.exists():
    print('matrix.csv missing', file=sys.stderr)
    sys.exit(2)
rows=list(csv.DictReader(p.open()))
(Path('../../.artifacts')/ 'matrix.json').write_text(json.dumps(rows, indent=2))
print('wrote matrix.json with', len(rows), 'rows')
PY

echo "Maturity check complete. Artifact: $(pwd)/../../.artifacts/matrix.json"
