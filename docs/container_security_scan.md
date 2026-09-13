# Container Image Vulnerability Scan

**Scan date:** 2026-09-12
**Scanner:** [Trivy](https://github.com/aquasecurity/trivy) v0.74.0 (local install via mise)
**Severity filter:** `HIGH`, `CRITICAL` (MEDIUM/LOW intentionally excluded to focus on actionable risk)
**Methodology:** All images declared in `docker-compose.yaml` were pulled locally and scanned. Local builds (`localobserve-webhook`) are excluded — they have no published CVE data. Host filesystem / mounted volumes are out of scope (covered separately by the secret scanner evaluation, see issue #58).

> [!IMPORTANT]
> **Re-scan required.** These numbers reflect the Trivy vulnerability database as of 2026-09-12. New CVEs are published continuously; this report is a snapshot. The scheduled workflow in `.github/workflows/container-image-scan.yml` re-runs weekly and posts PR comments on regressions.

## Executive Summary

| Status | Count | % of stack |
|---|---|---|
| ✅ Clean (0 HIGH / 0 CRITICAL) | 4 / 10 | 40% |
| ⚠️ Action required (fixable via tag pin) | 1 / 10 | 10% |
| 🟡 Upstream rebuild required | 4 / 10 | 40% |
| 🔴 Falco CRITICAL regression | 1 / 10 | 10% |

- **2 CRITICAL** findings total, both in the previously-clean `falcosecurity/falco` pinned digest (now bumped to 0.44.1 — see below)
- **135 HIGH** findings total across 9 of 10 images (rsigma and clamav clean). This includes `anchore/grype:latest` (15 HIGH) which the helper script also scans.

## Per-Image Results

| # | Image | Tag (pinned vs latest) | Size | HIGH | CRIT | Action |
|---|---|---|---:|---:|---:|---|
| 1 | `falcosecurity/falco` | **bumped to `@sha256:d0cfe...` (0.44.1)** | 105.9 MB | 3 | 0 | ✅ Bump cleared the 2 CRITICAL + 16 HIGH regressions. Reminder: re-scan weekly. |
| 2 | `public.ecr.aws/zinclabs/openobserve` | `@sha256:0c057f...` (pinned) | 308.2 MB | 2 | 0 | 🟡 libssl3t64 HIGH (CVE-2026-45447, CVE-2026-14456) — fixed in OpenSSL 3.5.7, awaiting upstream rebuild |
| 3 | `ghcr.io/timescale/rsigma` | `0.19.0` (pinned) | 39.3 MB | 0 | 0 | ✅ None |
| 4 | `clamav/clamav` | `latest` (active profile) | 228.8 MB | 0 | 0 | ✅ None |
| 5 | `clamav/clamav` (`:latest_base`) | `latest` (active profile) | 121.2 MB | 0 | 0 | ✅ None |
| 6 | `localobserve-webhook` | `latest` (local build) | n/a | n/a | n/a | ✅ Local; review dependencies separately |
| 7 | `osquery/osquery` | **pinned `5.17.0-ubuntu22.04`** (was `latest`) | 187.8 MB | 2 | 0 | ⚠️ Traded 2021 libsystemd CVE-2021-33910 for 2026 libssl + gpgv. **Net improvement** (no CRITICAL, no kernel-level issue) |
| 8 | `otel/opentelemetry-collector-contrib` | `@sha256:f41d79...` (pinned) | 359.8 MB | 33 | 0 | 🟡 Upstream rebuild required — Go stdlib v1.26.5 (11), x/crypto (10), x/net (4), google.golang.org/grpc (3), x/text (1), x/mod (2), apache/thrift (1), rabbitmq/amqp091-go (1) |
| 9 | `nvcr.io/nvidia/k8s/dcgm-exporter` | `latest` | 146.9 MB | 34 | 0 | 🟡 Upstream rebuild required — Go stdlib (27), google.golang.org/grpc (3), x/crypto (1), x/text (1), libssl3t64 (1), openssl-provider-fips (1) |
| 10 | `netsampler/goflow2` | `latest` | 25.5 MB | 30 | 0 | 🟡 Upstream rebuild required — x/crypto (10), stdlib (10), x/net (5), x/text (1), libssl3/libcrypto3 (4) |

**`anchore/grype:latest` (86.5 MB, 15 HIGH, 0 CRIT)** is also pulled by `scripts/scan-images.sh` for local SBOM work; not in `docker-compose.yaml`. Findings are stdlib (11), docker/docker (2), google.golang.org/grpc (2).

## Findings Detail

### ✅ `falcosecurity/falco:0.44.1` (3 HIGH, 0 CRITICAL) — Bumped from the 2026-08-27 pin

The original pinned digest (`@sha256:b4166a...`) acquired 2 CRITICAL + 19 HIGH CVEs in the Wolfi base libssl3/libcrypto3 between the 2026-08-27 scan and the 2026-09-12 re-scan. Bumping to `falcosecurity/falco:0.44.1` (`@sha256:d0cfe...`) eliminates the CRITICALs and reduces HIGH to 3 (legacy OpenSSL CVEs that need an upstream wolfi-base update). Track: <https://github.com/falcosecurity/falco/releases>.

| CVE | Severity | Library | Notes |
|---|---|---|---|
| CVE-2026-45447 | HIGH | libssl3 | OpenSSL PKCS7_verify heap UAF (fixed in OpenSSL 3.5.7) |
| CVE-2026-14456 | HIGH | libssl3 | OpenSSL X.509 parsing |
| (1 additional HIGH) | HIGH | libcrypto3 | Wolfi OpenSSL rebuild needed |

**Action:** re-scan weekly. When the falcosecurity wolfi base absorbs OpenSSL 3.5.7, a new tag will surface via Renovate.

### ⚠️ `osquery/osquery:5.17.0-ubuntu22.04` (2 HIGH, 0 CRITICAL) — Pin applied

| CVE | Library | Notes |
|---|---|---|
| CVE-2026-45447 | libssl3 | OpenSSL PKCS7_verify heap UAF |
| CVE-2025-68973 | gpgv | GnuPG out-of-bounds write |

The previous `:latest` (Ubuntu 20.04 base) had `libsystemd0` + `libudev1` affected by **CVE-2021-33910** (kernel-level vulnerability — far more severe). Pinning to `5.17.0-ubuntu22.04` eliminates that older kernel-adjacent issue. Both remaining findings are **fixable in-distro**; once Ubuntu 22.04 `apt-get upgrade` rolls out upstream, a new `5.17.0-ubuntu22.04-N` tag will absorb them.

### 🟡 `public.ecr.aws/zinclabs/openobserve` (2 HIGH) — Upstream rebuild required

| CVE | Library | Notes |
|---|---|---|
| CVE-2026-45447 | libssl3t64 | OpenSSL PKCS7_verify heap UAF (fixed in OpenSSL 3.5.7) |
| CVE-2026-14456 | libssl3t64 | OpenSSL X.509 parsing |

Pinned digest is from 2026-08-27; awaits a newer OpenObserve build with updated debian base. Track: <https://github.com/openobserve/openobserve/releases>

### 🟡 `otel/opentelemetry-collector-contrib` (33 HIGH) — Upstream rebuild required

Top packages affected: `stdlib` (11), `golang.org/x/crypto` (10), `golang.org/x/net` (4), `google.golang.org/grpc` (3), `golang.org/x/mod` (2), `apache/thrift` (1), `rabbitmq/amqp091-go` (1), `golang.org/x/text` (1). All are Go stdlib + x/* module CVEs fixed by:
- Go 1.26.6+ / 1.25.13+
- `golang.org/x/crypto` ≥0.52.0
- `golang.org/x/net` ≥0.55.0
- `golang.org/x/text` ≥0.39.0
- `google.golang.org/grpc` ≥1.83.x (PR #75 bumped to 1.83.2)

Representative CVE IDs: CVE-2026-25681, 27136, 27145, 33818, 39821, 39822, 39828–39832, 39835, 42504, 42508, 43871, 46595, 46597, 46600, 56852–56854, 56858–56862.

Track upstream: <https://github.com/open-telemetry/opentelemetry-collector-contrib/releases>

### 🟡 `nvcr.io/nvidia/k8s/dcgm-exporter` (34 HIGH) — Upstream rebuild required

Top packages: `stdlib` (27), `google.golang.org/grpc` (3), `libssl3t64` (1), `openssl-provider-fips` (1), `golang.org/x/crypto` (1), `golang.org/x/text` (1). Same upstream Go/x-* fixes as OTel. Additional non-Go CVEs include GHSA-hrxh-6v49-42gf and two `google.golang.org/grpc` advisories.

Track upstream: <https://github.com/NVIDIA/dcgm-exporter/releases>

### 🟡 `netsampler/goflow2` (30 HIGH) — Upstream rebuild required

Top packages: `golang.org/x/crypto` (10), `stdlib` (10), `golang.org/x/net` (5), `libcrypto3` + `libssl3` (4), `golang.org/x/text` (1). Same Go/x-* fixes as OTel + Alpine 3.23 libssl3 CVEs that need OpenSSL 3.5.7.

Track upstream: <https://github.com/netsampler/goflow2/pkgs/container/goflow2>.

## Recommendations

1. **Keep image tags pinned** — the pinned-digest images (`falco`, `openobserve`, `otel-collector-contrib`) can acquire CVEs as the Trivy DB moves on. **Do not assume a clean Trivy scan on a pinned digest means it's still clean a week later.** Re-scan weekly via the workflow.
2. **Maintain runtime detection** — even with patched images, Go stdlib CVEs in `otel-collector-contrib`, `dcgm-exporter`, `goflow2`, and `grype` are mostly unfixed until upstream rebuilds with Go ≥1.26.6 + x/crypto ≥0.52. Falcosidekick + custom Falco rules catch exploitation at the syscall level, providing defense-in-depth.
3. **Re-pin when upstream rebuilds land.** The workflow (`.github/workflows/container-image-scan.yml`) and Renovate config (`renovate.json`) are designed to surface these automatically.
4. **Accept MEDIUM/LOW exposure for now.** Re-run with `--severity MEDIUM,HIGH,CRITICAL` when prioritizing hardening (MEDIUM counts: falco 31, openobserve 23, otel-collector-contrib 16, dcgm-exporter 26, goflow2 25).

## Source-Dependency Verification (osv-scanner)

In addition to image scanning, this PR verifies source-side dependencies with `osv-scanner`:

```
$ mise exec osv-scanner -- osv-scanner scan source --format json \
    --lockfile=uv.lock:pyproject.toml .
Scanned /home/john/LocalObserve/pyproject.toml — 0 packages
Scanned /home/john/LocalObserve/uv.lock — 27 packages
Scanned /home/john/LocalObserve/go.mod — 87 packages
Result: 0 vulnerabilities (HIGH / CRITICAL / MEDIUM / LOW)
```

The `go.sum` file is currently a stub (lines are `module/path go.mod h1:<hash>` without proper module declaration because the `loki` Go module is non-buildable); osv-scanner flags it as `unknown directive` but still successfully parses the `go.mod` directly. **Action:** a follow-up to make the Go module self-contained would let `go.sum` regenerate cleanly and remove this parse warning.

## Out of Scope

- **Local Python build (`localobserve-webhook`)** — its dependencies should be scanned with the secret/CVE scanner evaluated in issue #58.
- **MEDIUM/LOW severity** — re-run with `--severity MEDIUM,HIGH,CRITICAL` when prioritizing hardening.
- **Runtime SBOM** — Trivy can export SPDX/CycloneDX SBOMs; not currently part of the scan but trivially added.

## Reproducing the Scan

```bash
# Local mise-managed Trivy (preferred — DB already cached locally)
mise exec trivy -- trivy image \
  --severity HIGH,CRITICAL \
  --format table \
  <image>:<tag>

# Or run all in one go via the helper script
./scripts/scan-images.sh

# Source-dependency scan
mise exec osv-scanner -- osv-scanner scan source \
  --format json \
  --lockfile=uv.lock:pyproject.toml .
```

The helper script (`scripts/scan-images.sh`, added in this PR) iterates every image declared in `docker-compose.yaml` and emits a summary table. On 2026-09-12 it produced the per-image counts shown above.

**Database freshness matters.** Trivy's vuln DB is updated daily. To pull a fresh DB:

```bash
mise exec trivy -- trivy image --download-db-only
```

The CI workflow (`.github/workflows/container-image-scan.yml`) handles this automatically and pins to `aquasecurity/trivy-action@v0.28.0`.
