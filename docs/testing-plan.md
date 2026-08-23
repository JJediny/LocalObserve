# LocalObserve System Testing Plan

## Scope and current architecture

The active stack is:

- Falco and osquery for runtime detection and host telemetry.
- OpenTelemetry Collector Contrib for file, OTLP, and metrics ingestion.
- OpenObserve for log, trace, and metric storage and querying.
- rsigma for Sigma evaluation and the optional Grype scanner profile.

This document describes the active OpenObserve + OTel path. Historical comparison
configuration is not part of the acceptance path below.

## Assumptions to verify

Every review or release should explicitly check these assumptions rather than
assuming that a green static test proves them:

1. `docker`, `podman`/`podman-remote`, and `nerdctl` are clients; their host
   engines are separately installed and running.
2. The Compose provider for each selected client accepts the repository's
   `docker-compose.yaml`, including privileged services, host PID/network modes,
   and `:z` bind labels.
3. osquery emits the fields consumed by the OTTL filter, including
   `body["log_type"]` for status records.
4. The external threat-intelligence feed paths and registry image references are
   reachable and have the expected formats when network-backed checks are run.
5. Rootless Podman/Nerdctl can run the core pipeline, but Falco kernel/eBPF
   coverage may require a rootful engine or host probe.

If an engine, network feed, or binary validator is unavailable, record that as a
blocked or skipped check; do not report it as verified.

The repository pins the Task runner in `mise.toml`. Bootstrap the toolchain and
invoke Task through mise on a fresh checkout:

```bash
mise trust
mise install
mise exec task -- task test
```

After enabling mise in the shell (`mise activate`), the shorter `task ...`
commands below are equivalent.

## 1. Hermetic static checks

These checks require no running containers and must remain safe in an air-gapped
checkout:

```bash
uv run python -m pytest tests/
```

The suite covers:

- JSON/YAML structure and detection-rule coverage for Falco and osquery.
- OTTL processor definitions and pipeline placement.
- Threat-intelligence normalization, cache fallback, and generated consumer
  fragments with mocked network calls.
- Grype result parsing and severity gating with sample JSON.
- Betterleaks configuration parsing and mise/Taskfile wiring.
- Compose resource limits, healthchecks, scan profiles, and runtime adapter
  contracts.

For a focused run after pipeline or runtime changes:

```bash
uv run python -m pytest \
  tests/test_otel_ottl.py \
  tests/test_runtime_acceptance.py \
  tests/test_infrastructure_health.py \
  tests/test_resource_limits.py -v
bash -n scripts/runtime-compose.sh scripts/verify-runtimes.sh tools/trigger-detections.sh
```

## 2. Tool and configuration validators

Run validators when the corresponding real binary is installed. These checks
exercise parsers that structural Python tests cannot replace:

```bash
otelcol --config otel-collector-config.yaml validate
betterleaks config check --config .betterleaks.toml
falco --list rules
python3 -m json.tool osqueryd.conf >/dev/null
```

`otelcol`, `betterleaks`, and `falco` are optional local validators. Their
absence is a recorded environment limitation, not a reason to weaken tests.
The repository-managed Betterleaks command is:

```bash
mise exec betterleaks -- betterleaks dir \
  --config .betterleaks.toml --redact --no-banner .
```

## 3. Compose configuration checks

Before booting, render the Compose model with each available provider. Rendering
can expose unsupported keys without creating containers:

```bash
docker compose config --quiet
podman compose config --quiet
nerdctl compose config --quiet
```

Run only the commands whose client and provider are installed. A successful
render is not an engine or kernel-capability check.

## 4. Cross-runtime boot and pipeline acceptance

The canonical live gate is:

```bash
task verify-runtimes
```

The harness tests each runtime with an isolated project name:

- `localobserve-docker`
- `localobserve-podman`
- `localobserve-nerdctl`

For each available engine it checks the published host ports, starts the core
stack, waits for services to be running and healthchecks to be healthy, executes
static detection checks, runs the runtime-aware `tools/trigger-detections.sh`
with the selected runtime, and removes the project and volumes on success or
failure. Missing clients, unavailable host engines, or occupied host ports are
reported as `SKIP`; Compose/provider errors and detection failures are failures.
Project names isolate engine objects, but they cannot isolate host port bindings.

Run an individual runtime manually when troubleshooting:

```bash
RUNTIME=docker COMPOSE_PROJECT_NAME=localobserve-docker \
  task trigger-detections
RUNTIME=podman COMPOSE_PROJECT_NAME=localobserve-podman \
  task trigger-detections
RUNTIME=nerdctl COMPOSE_PROJECT_NAME=localobserve-nerdctl \
  task trigger-detections
```

The trigger script defaults to Docker for standalone use, but honors `RUNTIME`
and `COMPOSE_PROJECT_NAME` for the cross-runtime harness. The webhook endpoint
can be changed with `ALERT_RECEIVER_URL` when the local port is remapped.

### Rootless caveat

Core pipeline acceptance (OpenObserve, OTel Collector, osquery, and rsigma) may
be run rootless. Falco's modern eBPF probe can require rootful Podman or Nerdctl
because rootless engines may not expose the required kernel interfaces. Record
that limitation separately from a core-stack failure.

## 5. Workstream-specific live checks

### OTTL reduction

1. Record a baseline ingest volume for a fixed interval.
2. Inject a representative osquery status record and a security-relevant FIM or
   Falco record.
3. Query OpenObserve and verify status noise is absent while the security record
   remains present.
4. Record the measured non-zero reduction; do not claim the plan's 20% target
   without measurements.

### Threat-intelligence sync

```bash
task sync-threat-intel
uv run python tools/sync_threat_intel.py --dry-run
```

Use mocked feeds for unit tests. For a live run, verify the raw feed URLs first,
then confirm the generated files are visible in the Falco and osquery mounts and
that Falco can load the generated list fragment. Test the offline path by
blocking or replacing the feed URLs and confirming cached data is retained.

### Image and registry scanning

The scanner is opt-in and must not enlarge the default runtime stack:

```bash
task scan-image RUNTIME=docker IMAGE=alpine:3.10
task scan-image RUNTIME=podman IMAGE=alpine:3.10
task scan-image RUNTIME=nerdctl IMAGE=alpine:3.10
```

These checks require an engine, the scanner image, and registry access. Verify a
parseable JSON result and the expected non-zero exit for critical/high findings.
Run an unreachable-registry case separately and confirm it fails clearly without
silently treating a missing result as a clean scan.

## 6. Acceptance checklist

- [ ] `uv run python -m pytest tests/` passes.
- [ ] Shell syntax checks pass for changed scripts.
- [ ] Available real-binary validators pass.
- [ ] Compose config renders on each available runtime.
- [ ] `task verify-runtimes` passes on Docker, Podman, and Nerdctl, or each
      unavailable engine is documented as skipped.
- [ ] Core pipeline detection triggers pass on all tested runtimes.
- [ ] Falco rootless/eBPF limitations are recorded separately when applicable.
- [ ] Threat-intel feed paths and osquery log-field semantics are verified before
      marking their live acceptance items complete.
- [ ] Scanner image/registry behavior is tested with network and error cases.
- [ ] No generated `.data/`, credentials, or host-specific artifacts are committed.
