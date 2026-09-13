#!/usr/bin/env bash
#
# scan-images.sh — Run Trivy vulnerability scan against every image declared
# in docker-compose.yaml. Used by CI (.github/workflows/container-image-scan.yml)
# and developers reproducing the scan documented in
# docs/container_security_scan.md.
#
# Exit codes:
#   0 — all images scanned (regardless of findings; informational)
#   1 — Trivy unavailable, no images found, or hard CRITICAL gate tripped
#       when STRICT=1 is set
#
# Environment:
#   TRIVY_IMAGE     container image to run Trivy in (default: aquasec/trivy:latest)
#   SEVERITY        comma-separated severities to scan (default: HIGH,CRITICAL)
#   COMPOSE_FILE    docker-compose file to read image list from (default: docker-compose.yaml)
#   STRICT          if set to 1, exit non-zero when any CRITICAL is found
#   TRIVY_CACHE_HOST host-side Trivy cache directory (default: $HOME/.cache/trivy)

set -euo pipefail

TRIVY_IMAGE="${TRIVY_IMAGE:-aquasec/trivy:latest}"
SEVERITY="${SEVERITY:-HIGH,CRITICAL}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yaml}"
# Host-side Trivy cache directory (read-write so fanal can build its per-image
# cache). Falls back to ~/.cache/trivy on Linux, ~/Library/Caches/trivy on macOS.
TRIVY_CACHE_HOST="${TRIVY_CACHE_HOST:-$HOME/.cache/trivy}"

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

if ! command -v docker >/dev/null 2>&1; then
  echo "docker CLI not found on PATH — cannot run Trivy container."
  echo "Install mise tools (trivy) and rerun with the local binary instead."
  exit 1
fi

# Prepare the host-side Trivy cache. Trivy needs RW access to this directory
# so its fanal cache (per-image layer metadata) can be persisted across runs.
mkdir -p "$TRIVY_CACHE_HOST"

DOCKER_RUN_TRIVY=(docker run --rm
  -v "$TRIVY_CACHE_HOST:/root/.cache/trivy"
  "$TRIVY_IMAGE")

# Make sure the trivy DB is fresh so findings are reproducible.
echo "Ensuring Trivy DB is up to date..."
"${DOCKER_RUN_TRIVY[@]}" image --download-db-only >/dev/null

echo ""
echo "Scanning ${#IMAGES[@]} images with Trivy ($SEVERITY)"
echo "=========================================="

total_high=0
total_crit=0
failed=0

for image in "${IMAGES[@]}"; do
  echo ""
  echo "▶ $image"
  echo "----------------------------------------------"

  # One docker run produces JSON. We redirect stdout to capture JSON,
  # but discard stderr (Trivy's INFO/WARN lines) so the JSON parser
  # doesn't choke on log lines.
  if ! out="$("${DOCKER_RUN_TRIVY[@]}" image \
        --skip-db-update \
        --severity "$SEVERITY" \
        --format json \
        "$image" 2>/dev/null)"; then
    echo "  ⚠️  Trivy failed for $image (likely network or auth)"
    failed=$((failed + 1))
    continue
  fi

  # Extract counts from JSON output. Trivy emits a top-level array of one
  # element; sometimes it returns an object. Handle both.
  read -r high crit <<<"$(echo "$out" | python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw)
except Exception:
    print("0 0")
    sys.exit(0)
if isinstance(data, list):
    data = data[0] if data else {}
high = crit = 0
for r in (data.get("Results") or []):
    for v in (r.get("Vulnerabilities") or []):
        sev = v.get("Severity","")
        if sev == "HIGH":    high  += 1
        elif sev == "CRITICAL": crit += 1
print(f"{high} {crit}")
' 2>/dev/null)"

  high=${high:-0}
  crit=${crit:-0}
  total_high=$((total_high + high))
  total_crit=$((total_crit + crit))
  echo "  → HIGH=$high  CRITICAL=$crit"
done

echo ""
echo "=========================================="
echo "Summary: HIGH=$total_high  CRITICAL=$total_crit  Failed=$failed"

if [[ "${STRICT:-0}" == "1" && "$total_crit" -gt 0 ]]; then
  echo "STRICT=1 set — exiting non-zero on CRITICAL findings."
  exit 1
fi
exit 0