# LocalObserve — Remaining Work Implementation Plan

> Generated from a review of **open issues** and **recent merged PRs** in
> `JJediny/LocalObserve` (via `gh`). Last reviewed: 2026-08-23.
>
> Goal: define the remaining work, with **acceptance criteria** that can be
> **verified locally on Docker, Podman, and Nerdctl** (the three runtimes the
> stack already advertises support for in `README.md` and `docker-compose.yaml`).

---

## 0. Implementation Status (as of 2026-08-23)

All four workstreams below are **implemented and open as PR #59**
(`feat/implement-plan-workstreams`). This section tracks what landed and the
remaining acceptance work that must be closed before merge.

### Done
- **#50 OTTL reduction** — `filter/drop_osquery_status` (osquery-only) +
  `transform/redact_large_payloads` added to `otel-collector-config.yaml`.
- **#51 Threat-intel sync** — `tools/sync_threat_intel.py` + `task sync-threat-intel`
  + default Falco fragment; offline-safe.
- **#57 Image scanner** — Grype `scanner` service (`scan` profile) +
  `task scan-image` / `task scan-registry`.
- **#58 Secret scanner** — switched to **betterleaks via mise** (`.betterleaks.toml`,
  `task secret-scan`); `betterleaks = "1.8.1"` added to `mise.toml`.
- **Cross-runtime harness** — `scripts/verify-runtimes.sh` (`task verify-runtimes`).
- **Agent instructions** — `AGENTS.md` documents "review and test assumptions".

### Remaining (acceptance gate — verify on Docker, Podman, Nerdctl)
- [ ] **Run `task verify-runtimes`** on a host with the engines (dockerd /
      containerd / podman machine). Could NOT run in the sandbox (no daemon).
- [ ] **Confirm the 5 unverified assumptions** from `AGENTS.md`: real
      `mthcht/awesome-lists` raw URLs, osquery `log_type` field schema,
      mise = CLIs only, podman-remote on Linux, engines not guaranteed in CI.
- [ ] **Close the 4 critical review findings on PR #59** (review comment):
      keep `filter/drop_osquery_status` osquery-only (addressed in working tree),
      make `scan` tasks runtime-agnostic (addressed in working tree),
      fix `verify-runtimes` health-check empty-value handling (addressed in working tree),
      and confirm `osqueryd.conf` `%%` vs `%` `file_paths` semantics on live osquery
      (still needs daemon validation).

---

## 1. Context: What Landed vs. What's Open

### 1.1 Recent merged work (baseline — do not regress)

| PR   | Title | Relevance to this plan |
|------|-------|------------------------|
| #47  | `feat: container standardization and privileged sidecars` | Distroless core images; `privileged` osquery/falco sidecars. Sets the runtime contract the new work must honor. |
| #56  | `docs: update container runtime support for podman and nerdctl compose` | Documented the 3-runtime story; acceptance must keep all three booting. |
| #52–#54 | `rsigma` configuration engine, daemon sidecar, image tag fix | `rsigma` daemon now runs in `docker-compose.yaml`; new feed/sync code should reuse the same plumbing. |
| `af64e5f` / `2c4e8f5` | Docker Desktop compatibility | `pid: host` + `network_mode: host` + optional `docker.sock` mount patterns that each runtime handles differently (see §5). |
| `42a8868` | osquery/falco host-vs-container parity verification tests | Added `tests/test_parity_osquery_falco.py` — reference pattern for cross-runtime verification. |

### 1.2 Open issues = the remaining work

| Issue | Type | Title | Theme |
|-------|------|-------|-------|
| [#50](https://github.com/JJediny/LocalObserve/issues/50) | Refactor | Standardize OTel Collector Filtering & Reduction via OTTL | Pipeline efficiency |
| [#51](https://github.com/JJediny/LocalObserve/issues/51) | Feature | Implement Threat Intelligence Keyword Sync from `mthcht/awesome-lists` | Threat intel |
| [#57](https://github.com/JJediny/LocalObserve/issues/57) | Feature | Container Scanner and Registry (Grype / Trivy) | Image/registry scanning |
| [#58](https://github.com/JJediny/LocalObserve/issues/58) | Evaluate | Secret Scanner (ggshield, betterleaks, trufflehog, ripsecrets, kingfisher, gitleaks) | Pre-commit / pipeline secret detection |

> **Stale-doc note:** `docs/testing-plan.md` still describes the *legacy Loki/Alloy*
> pipeline (`alloy-local-config.yaml`, `falcosidekick -> loki-write`). The live
> stack is OpenObserve + OTel Collector (`otel-collector-config.yaml`). Any new
> acceptance tests must target the **OTel pipeline**, and `docs/testing-plan.md`
> should be refreshed as part of this plan (see §6).

---

## 2. Workstream A — Issue #50: OTTL Filtering & Reduction

**Goal:** Drop high-volume, low-priority system logs at the OTel Collector source
using OpenTelemetry Transformation Language (OTTL) processors, reducing indexing
size and network load on OpenObserve.

### 2.1 Approach
- Add `filter` / `transform` processors to `otel-collector-config.yaml`.
- Identify drop candidates from the current volume baseline (osquery `process_events`,
  repeated `syslog` noise, ClamAV heartbeat lines) — quantify before/after.
- Keep all security-relevant streams (Falco alerts, osquery FIM, rsigma hits,
  GoFlow2 netflow) untouched.
- Document each drop rule with the rationale and the OTTL condition.

### 2.2 Implementation steps
1. Stand up the stack and baseline ingest volume (see §5) → record MB/hr in OpenObserve.
2. Draft OTTL `transform` (redact/lower severity) and `filter` (drop) processors.
3. Add a new config fragment under `otel-collector-config.yaml` gated by comments.
4. Add a unit check in `tests/` asserting the collector config loads and the
   processors are present (`test_infrastructure_health.py` is the natural home).
5. Update `docs/optimization.md` with the measured reduction.

### 2.3 Acceptance criteria
- [ ] `otel-collector` healthcheck passes on **Docker, Podman, and Nerdctl** (see §5 matrix).
- [ ] A synthetic "noisy" log line matching a drop rule is **absent** from OpenObserve
      after ingestion, while a "critical" line (Falco/osquery FIM) is **present**.
- [ ] Measured ingest volume drops by a documented, non-zero amount vs. baseline (target ≥ 20%).
- [ ] `uv run python -m pytest tests/ -k "otel or infrastructure" -v` is green.
- [ ] No security event type is dropped (verified via `task trigger-detections`).

---

## 3. Workstream B — Issue #51: Threat-Intel Keyword Sync

**Goal:** A lightweight, cron-runnable script (`tools/sync_threat_intel.py`) that
periodically fetches Tor/VPN IPs, bad User-Agents, named pipes, and ransomware
extensions from [`mthcht/awesome-lists`](https://github.com/mthcht/awesome-lists)
and publishes them into **shared container volumes** consumed by osquery, Falco,
and the OTel Collector.

### 3.1 Approach
- New `tools/sync_threat_intel.py` (Python, `uv`-managed like `tools/parse_mitre_stix.py`).
- Write artifacts to a new shared volume (e.g. `.data/threat-intel/`) mounted
  read-only into `osquery`, `falco`, and `otel-collector` (mirror the existing
  `.:z` bind-mount pattern from `docker-compose.yaml`).
- Map outputs to each consumer:
  - **osquery:** a dynamic table / file-backed lookup (e.g. `osquery.conf` `file_paths` + `python_plugins` or a CSV autoload).
  - **Falco:** a `list`/`macro` referencing the generated file.
  - **OTel:** optional enrichment attribute from the file.
- Network-failure safe: cache last-good file, fail closed, no crash on offline runs.

### 3.2 Implementation steps
1. Scaffold `tools/sync_threat_intel.py` with a `--dry-run` and `--output-dir`.
2. Add a compose volume + mount to `docker-compose.yaml` for the three consumers.
3. Add the osquery `file_paths` entry and a Falco list referencing the generated files.
4. Add a `Taskfile` task `sync-threat-intel` and a cron example in `docs/deployment.md`.
5. Add `tests/test_threat_intel_sync.py`: offline mock fetch → assert file formats + consumer config validity.

### 3.3 Acceptance criteria
- [ ] Script runs with `--dry-run` and real run; writes well-formed files to `.data/threat-intel/`.
- [ ] With network blocked, the script exits 0 using cached data and logs a warning (offline-safe).
- [ ] `osquery` container starts and the dynamic file-backed table is queryable.
- [ ] `falco` rule referencing the generated list loads (`falco --list rules` clean) on all 3 runtimes.
- [ ] `tests/test_threat_intel_sync.py` passes; `task test-detection-coverage` still green.
- [ ] Works identically under **Docker, Podman, and Nerdctl** (shared volume present & mounted `:z`).

---

## 4. Workstream C — Issue #57: Container Image & Registry Scanner

**Goal:** Integrate an image/registry scanner (Grype or Trivy) into the stack so
images (local or a target registry) are scanned and results land in OpenObserve.

### 4.1 Approach
- Choose **Grype** (SBOM-less direct image scan, simple JSON, low footprint) or
  **Trivy** (broader: image + filesystem + misconfig + registry). Decision
  documented in `docs/`. Recommendation: start with **Grype** for image CVEs,
  keep Trivy as the registry/filesystem option.
- Add a `scan` **profile** service in `docker-compose.yaml` (consistent with the
  existing `clamav`/`clamav-scanner` `scan` profile pattern) so it is opt-in.
- Scanner emits JSON to a shared log volume (e.g. `.data/scanner/`) consumed by
  the OTel Collector file receiver → OpenObserve, or posts directly to the
  `alert-receiver` webhook on `:9000`.

### 4.2 Implementation steps
1. Add `scanner` service (`anchore/grype` or `aquasec/trivy`) under `profiles: [scan]`.
2. Wire output to OTel (`filelog` receiver) or `alert-receiver` (documented choice).
3. Add `Taskfile` tasks: `scan-image IMAGE=...` and `scan-registry REGISTRY=...`.
4. Add `tests/test_image_scanner.py`: assert container starts, scans a tiny target
   image, and produces parseable JSON (mock the network for registry scans).
5. Document enabling via `docker compose --profile scan up -d scanner` and the
   Podman/Nerdctl equivalents.

### 4.3 Acceptance criteria
- [ ] `scanner` service starts under the `scan` profile on **all 3 runtimes**.
- [ ] Scanning a known-vulnerable test image (e.g. `alpine:3.10`) yields a non-empty
      JSON result with at least one CVE.
- [ ] Result reaches OpenObserve (via OTel) **or** triggers `alert-receiver` (verified
      with `task test-alerts` pattern).
- [ ] Registry scan path has an offline/error-handling test (no crash on unreachable registry).
- [ ] `tests/test_image_scanner.py` passes; no regression in `task test`.

---

## 5. Cross-Runtime Verification Matrix (Docker / Podman / Nerdctl)

This is the central acceptance gate: **every workstream must boot and pass its
checks on all three runtimes.** Use isolated project names so multiple runtimes
can be tested on one host without collision.

### 5.1 Universal boot + health check

```bash
# Run once per runtime: docker | podman | nerdctl
RT=docker
case "$RT" in
  docker)  C="docker compose";;
  podman)  C="podman compose";;   # or: podman-compose
  nerdctl) C="nerdctl compose";;
esac

$C -p localobserve-$RT up -d
# Wait for all healthchecks to report healthy:
$C -p localobserve-$RT ps --format '{{.Name}} {{.State}} {{.Health}}'
$C -p localobserve-$RT down -v
```

> For **Podman/Nerdctl rootless**, Falco's modern-eBPF probe may fail to attach
> (see `docs/podman_and_lima.md`). For full kernel syscall coverage, run `falco`
> **rootful** (`sudo podman compose ...` / `sudo nerdctl compose ...`) while the
> rest of the stack stays rootless. Acceptance for the *core pipeline* (OpenObserve,
> OTel, osquery, rsigma) must pass rootless; Falco-only checks are allowed to
> require rootful and must be called out.

### 5.2 Per-runtime gotchas to assert in CI / local runs

| Concern | Docker | Podman (rootless) | Nerdctl (rootless) |
|---------|--------|-------------------|--------------------|
| Compose driver | `docker compose` | `podman compose` / `podman-compose` | `nerdctl compose` |
| `pid: host` + `network_mode: host` (falco/osquery) | ✅ native | ⚠️ often needs rootful | ⚠️ often needs rootful |
| SELinux `:z` bind labels | ignored (harmless) | ✅ required on SELinux hosts | ✅ required on SELinux hosts |
| `docker.sock` optional mount | ✅ | map podman socket via `DOCKER_HOST=unix:///run/user/$(id -u)/podman/podman.sock` | N/A (containerd) |
| GPU `runtime: nvidia` profile | ✅ (opt-in) | ⚠️ requires nvidia-container-toolkit | ⚠️ requires nvidia-container-toolkit |
| Healthchecks / `depends_on` | ✅ | ✅ | ✅ |

### 5.3 Shared static + dynamic verification (runtime-agnostic)

```bash
# Static detection/coverage (no live stack required for most):
uv run python -m pytest \
  tests/test_detection_coverage.py tests/test_falco_rules.py tests/test_osquery_config.py -v

# Resource-limit guard (ensures every service still declares mem/cpu bounds):
uv run python -m pytest tests/test_resource_limits.py -v

# Live: trigger detections end-to-end through the running stack:
task trigger-detections          # falco/osquery -> otel -> openobserve
task test-host-emulation         # CALDERA safe ability + OTel trace verify
```

### 5.4 Definition of Done (global)
- [ ] Stack boots to **healthy** on Docker, Podman, and Nerdctl (per §5.1).
- [ ] Each workstream's acceptance checklist (§2.3 / §3.3 / §4.3) is met on all three.
- [ ] `task test` (osquery + falco + detection-coverage) is green on all three.
- [ ] No new `:z`/rootless/`network_mode` regressions introduced for any runtime.
- [ ] `docs/testing-plan.md` updated to reflect the OTel (not Loki) pipeline.

---

## 6. Testing Layout (reference)

| Test file | What it covers | Use for |
|-----------|----------------|---------|
| `tests/test_detection_coverage.py` | MITRE tagging + structural coverage (Falco/osquery) | #50, #51 config validity |
| `tests/test_falco_rules.py` | Falco rule schema/load | #50, #51 list load |
| `tests/test_osquery_config.py` | osqueryd.conf schema | #51 dynamic table |
| `tests/test_resource_limits.py` | compose `mem_limit`/`cpus` enforcement | §5.2 guard |
| `tests/test_parity_osquery_falco.py` | host-vs-container parity | cross-runtime pattern reference |
| `tests/test_infrastructure_health.py` | service health | #50 collector health |
| `tests/test_stack_integration.py` | E2E pipeline traversal | live verification |

`Taskfile` entry points: `task test`, `task test-detection-coverage`,
`task trigger-detections`, `task test-host-emulation`, `task test-alerts`,
`task sync-oo-import`.

---

## 7. Dependencies, Risks & Open Questions

- **#58 is an *evaluation*, not an implementation.** Deliverable is a written
  comparison + benchmark + recommendation (and optionally a PoC wiring
  `gitleaks`/`trufflehog` into the pipeline), not a permanent service. Suggested
  acceptance: `docs/secret-scanner-evaluation.md` with benchmark numbers and a
  chosen integration path; PoC added only if it fits the OTel/webhook model.
- **Network egress** for #51 (awesome-lists) and #57 (registry) must be
  offline-safe; CI runners may be air-gapped — mock in tests.
- **Runtime parity risk:** rootless eBPF (Falco) is the single biggest cross-runtime
  gap. Decide explicitly whether acceptance allows rootful Falco or documents the
  reduced-coverage mode for rootless.
- **OTTL baseline (§2.1)** should be captured *before* writing drop rules so the
  reduction claim is evidence-based, not assumed.
- **Stale docs:** `docs/testing-plan.md` (Loki/Alloy) should be reconciled with the
  OpenObserve+OTel reality as part of this plan.

## 8. Appendix — Commands Summary

```bash
# Recent PRs reviewed (context only): gh pr list --state all --limit 40
# Open issues:                gh issue list --state open
# Boot on each runtime:       see §5.1 loop
# Full local suite:           task test
```
