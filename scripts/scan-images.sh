#!/usr/bin/env bash
#
# scan-images.sh — Run Trivy vulnerability scan against every image declared
# in docker-compose.yaml. Used by CI (.github/workflows/trivy-scan.yml) and
# developers reproducing the scan documented in docs/container_security_scan.md.
#
# Exit codes:
#   0 — all images clean (0 HIGH, 0 CRITICAL)
#   1 — at least one image has HIGH or CRITICAL findings (informational;
#       hard gating is left to the CI workflow's `--exit-code` policy)

set -euo pipefail

TRIVY_IMAGE="${TRIVY_IMAGE:-aquasec/trivy:latest}"
SEVERITY="${SEVERITY:-HIGH,CRITICAL}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yaml}"

# Extract image:tag from compose. Skips comments, lines without image:, and
# local builds (no public tag).
mapfile -t IMAGES < <(
  grep -E '^\s+image:\s+' "$COMPOSE_FILE" \
    | sed -E 's/^\s+image:\s+//' \
    | sed -E 's/^\s+//' \
    | grep -vE '^\s*#' \
    | grep -v 'localobserve-webhook' \
    || true
)

if [[ ${#IMAGES[@]} -eq 0 ]]; then
  echo "No images found in $COMPOSE_FILE"
  exit 1
fi

echo "Scanning ${#IMAGES[@]} images with Trivy ($SEVERITY)"
echo "=========================================="

total_high=0
total_crit=0
failed=0

for image in "${IMAGES[@]}"; do
  echo ""
  echo "▶ $image"
  echo "----------------------------------------------"

  # --quiet suppresses header banner; we show our own.
  if ! docker run --rm "$TRIVY_IMAGE" image \
        --severity "$SEVERITY" \
        --quiet \
        --format table \
        "$image" 2>&1; then
    echo "  ⚠️  Trivy failed for $image (likely network or auth)"
    failed=$((failed + 1))
    continue
  fi

  # Capture counts for summary.
  counts="$(docker run --rm "$TRIVY_IMAGE" image \
              --severity "$SEVERITY" \
              --quiet \
              --format json \
              "$image" 2>/dev/null || echo '{}')"

  high=$(echo "$counts" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
print(sum(len([v for v in (r.get('Vulnerabilities') or []) if v.get('Severity') == 'HIGH'])
            for r in data.get('Results', [])))
" 2>/dev/null || echo 0)
  crit=$(echo "$counts" | python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
print(sum(len([v for v in (r.get('Vulnerabilities') or []) if v.get('Severity') == 'CRITICAL'])
            for r in data.get('Results', [])))
" 2>/dev/null || echo 0)

  total_high=$((total_high + high))
  total_crit=$((total_crit + crit))
done

echo ""
echo "=========================================="
echo "Summary: HIGH=$total_high  CRITICAL=$total_crit  Failed=$failed"

if [[ "$total_crit" -gt 0 ]]; then
  exit 1
fi
exit 0
