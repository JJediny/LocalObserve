#!/usr/bin/env bash
set -euo pipefail

# Dynamically resolve repository root based on script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Ensure submodules are initialized
git submodule update --init --recursive

FRAMEWORK_DIR="tools/detection-engineering-ai-maturity"
cd "$FRAMEWORK_DIR"

# Build site
if command -v npm >/dev/null 2>&1; then
  npm ci
  npm run build
else
  echo "npm not available; skipping site build"
fi

# Export paths as environment variables for Python block
export MATRIX_CSV="public/assets/matrix.csv"
export MATRIX_JSON="$REPO_ROOT/.artifacts/matrix.json"

mkdir -p "$(dirname "$MATRIX_JSON")"

python3 - <<'PY'
import csv, json, os, sys
from pathlib import Path

csv_path = Path(os.environ['MATRIX_CSV'])
json_path = Path(os.environ['MATRIX_JSON'])

if not csv_path.exists():
    print(f"matrix.csv missing at {csv_path}", file=sys.stderr)
    sys.exit(2)

rows = list(csv.DictReader(csv_path.open()))
json_path.write_text(json.dumps(rows, indent=2))
print(f"wrote matrix.json with {len(rows)} rows to {json_path}")
PY

echo "Maturity check complete. Artifact: $MATRIX_JSON"
