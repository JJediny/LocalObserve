#!/usr/bin/env bash
# Validate the OTel collector config with the same pinned image the stack runs.
set -u
out="${1:-.artifacts/otel_validate.txt}"
docker run --rm \
  -v "$PWD/otel-collector-config.yaml:/cfg/config.yaml:ro" \
  --entrypoint /otelcol-contrib \
  otel/opentelemetry-collector-contrib@sha256:f41d7995565df3733b7568702073a9c490792f9c6ac60684fe6a4da21a313f8d \
  validate --config /cfg/config.yaml >"$out" 2>&1
rc=$?
echo "otelcol validate exit=$rc (output in $out)"
exit $rc
