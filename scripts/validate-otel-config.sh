#!/usr/bin/env bash
# Validate the OTel collector config with the same pinned image the stack runs.
set -euo pipefail
out="${1:-.artifacts/otel_validate.txt}"
mkdir -p "$(dirname "$out")"
IMAGE=$(grep -A 2 "otel-collector:" docker-compose.yaml | grep "image:" | awk '{print $2}')
docker run --rm \
  -v "$PWD/otel-collector-config.yaml:/cfg/config.yaml:ro" \
  --entrypoint /otelcol-contrib \
  "${IMAGE:-otel/opentelemetry-collector-contrib@sha256:fd328de2552466ad78385e1b1289c3f2402b1c45f265b252aab1955b42845ac1}" \
  validate --config /cfg/config.yaml >"$out" 2>&1
rc=$?
echo "otelcol validate exit=$rc (output in $out)"
exit $rc
