# Container Image Vulnerability Scan

**Scan date:** 2026-09-28 (full stack) · **2026-10-03** (`localobserve-webhook` rebuild verification)
**Scanner:** [Trivy](https://github.com/aquasecurity/trivy) v0.74.0 (local install via Docker / mise)
**Severity filter:** `HIGH`, `CRITICAL` (MEDIUM/LOW intentionally excluded to focus on actionable risk)
**Methodology:** All images declared in `docker-compose.yaml` were pulled locally and scanned. The self-built `localobserve-webhook` image is included as of 2026-10-03: Trivy's `gobinary` scanner reads the Go module and stdlib info embedded in the compiled webhook binary, so local builds have real vulnerability findings too. Host filesystem / mounted volumes are out of scope (covered separately by the secret scanner evaluation, see issue #58).

> [!IMPORTANT]
> **Re-scan required.** These numbers reflect the Trivy vulnerability database as of 2026-09-28. New CVEs are published continuously; this report is a snapshot. The scheduled workflow in `.github/workflows/container-image-scan.yml` re-runs weekly and posts PR comments on regressions.

## Executive Summary

| Status | Count | % of stack |
|---|---|---|
| ✅ Clean (0 HIGH / 0 CRITICAL) | 7 / 10 | 70% |
| ⚠️ Action required (fixable via tag pin) | 0 / 10 | 0% |
| 🟡 Upstream rebuild required (profile-gated) | 3 / 10 | 30% |
| 🔴 Falco CRITICAL regression | 0 / 10 | 0% |

- **0 CRITICAL** findings total across all images in the entire stack.
- **66 HIGH** findings total across auxiliary profile-gated images (`dcgm-exporter`, `goflow2`, `osquery`). The core stack (`openobserve`, `otel-collector`, `rsigma`, `falco`) is **100% clean of HIGH and CRITICAL CVEs**; `clamav` acquired 1 HIGH (pcre2 CVE-2026-103111) via floating-tag drift in October 2026 and is now digest-pinned — see [#111](https://github.com/JJediny/LocalObserve/issues/111) and the update below.
- **Webhook rebuild verified (2026-10-03):** replacing the prebuilt `almir/webhook` runtime base with a from-source build (`go install github.com/adnanh/webhook@2bbdeb9f90b5` — the 2026-09-04 commit whose `version.go` reports 2.8.3 — on `golang:alpine`, **Go 1.27.1**, on a pinned Alpine 3.24 base) cut fixable findings from **2 CRITICAL / 37 HIGH → 0 / 0**. Upstream tags carry no `v` prefix and stop at 2.6.11, so semver pins like `@v2.8.3` are unresolvable; the build pins the commit instead and installs `git` in the builder for the direct VCS fetch. See [Webhook source rebuild](#-localobserve-webhook-0-high-0-critical--rebuilt-from-source-go-1271-2026-10-03).

## Per-Image Results

| # | Image | Tag (pinned vs latest) | Size | HIGH | CRIT | Action |
|---|---|---|---:|---:|---:|---|
| 1 | `falcosecurity/falco` | **bumped to `@sha256:788f1...` (0.45.0)** | 105.9 MB | 0 | 0 | ✅ Clean. Zero HIGH / CRITICAL findings. |
| 2 | `openobserve/openobserve` | **bumped to `@sha256:d4a87...` (1.0.4)** | 308.2 MB | 0 | 0 | ✅ Clean. Zero HIGH / CRITICAL findings. |
| 3 | `ghcr.io/timescale/rsigma` | `0.19.0` (pinned) | 39.3 MB | 0 | 0 | ✅ None |
| 4 | `clamav/clamav` | **pinned `latest@sha256:7659d…` (2026-10-04, was `latest`)** | 240 MB | 1 | 0 | ⚠️ pcre2 CVE-2026-103111 entered via floating-tag drift; now digest-pinned — see [#111](https://github.com/JJediny/LocalObserve/issues/111). |
| 5 | `clamav/clamav` (`:latest_base`) | **pinned `latest_base@sha256:4bd75…` (2026-10-04)** | 127 MB | 1 | 0 | ⚠️ Same pcre2 finding — #111. |
| 6 | `localobserve-webhook` | **rebuilt from source** (`webhook@2bbdeb9f90b5` ≈ v2.8.3 on `golang:alpine` → pinned Alpine 3.24) | 81 MB | 0 | 0 | ✅ Clean. Was 2 CRIT / 37 HIGH on `almir/webhook:latest` before the rebuild (2026-10-03). |
| 7 | `osquery/osquery` | **pinned `5.17.0-ubuntu22.04`** | 187.8 MB | 2 | 0 | ⚠️ 2 in-distro base CVEs (libssl3, gpgv). No CRITICAL; profile-gated to `agents`. |
| 8 | `otel/opentelemetry-collector-contrib` | **bumped to `@sha256:fd328...` (0.161.0)** | 359.8 MB | 0 | 0 | ✅ Clean. Zero HIGH / CRITICAL findings (RabbitMQ & stdlib CVEs resolved). |
| 9 | `nvcr.io/nvidia/k8s/dcgm-exporter` | `latest` | 146.9 MB | 34 | 0 | 🟡 Upstream rebuild required (Go stdlib & grpc). Gated to `gpu` profile. |
| 10 | `netsampler/goflow2` | `latest` | 25.5 MB | 30 | 0 | 🟡 Upstream rebuild required (Go stdlib & x/crypto). Gated to `netflow` profile. |

**`anchore/grype:latest` (86.5 MB, 11 HIGH, 0 CRIT)** is also pulled by `scripts/scan-images.sh` for optional vulnerability scanning; gated behind `--profile scan`.

## Findings Detail

### ✅ `falcosecurity/falco:0.45.0` (0 HIGH, 0 CRITICAL) — Bumped to sha256:788f1129...

Bumping to `falcosecurity/falco:0.45.0` eliminates all previous Wolfi OpenSSL CVEs.

### ✅ `openobserve/openobserve:1.0.4` (0 HIGH, 0 CRITICAL) — Bumped to sha256:d4a878fa...

Upgraded to 1.0.4; Debian 13.7 base resolves all libssl3 CVEs (CVE-2026-45447, CVE-2026-14456).

### ✅ `otel/opentelemetry-collector-contrib:0.161.0` (0 HIGH, 0 CRITICAL) — Bumped to sha256:fd328de2...

Upgraded to 0.161.0; resolves all Go stdlib, x/crypto, and amqp091-go CVEs.

### ⚠️ `osquery/osquery:5.17.0-ubuntu22.04` (2 HIGH, 0 CRITICAL) — Pin applied

| CVE | Library | Notes |
|---|---|---|
| CVE-2026-45447 | libssl3 | OpenSSL PKCS7_verify heap UAF |
| CVE-2025-68973 | gpgv | GnuPG out-of-bounds write |

The previous `:latest` (Ubuntu 20.04 base) had `libsystemd0` + `libudev1` affected by **CVE-2021-33910** (kernel-level vulnerability — far more severe). Pinning to `5.17.0-ubuntu22.04` eliminates that older kernel-adjacent issue. Both remaining findings are **fixable in-distro**; once Ubuntu 22.04 `apt-get upgrade` rolls out upstream, a new `5.17.0-ubuntu22.04-N` tag will absorb them.

### ✅ `localobserve-webhook` (0 HIGH, 0 CRITICAL) — Rebuilt from source (Go 1.27.1, 2026-10-03)

The alert receiver previously shipped the prebuilt `almir/webhook:latest` binary, which
embedded an **end-of-life Go toolchain** and its own Alpine OpenSSL. Trivy (`--severity
HIGH,CRITICAL --ignore-unfixed --scanners vuln`, same settings as CI) against the
baseline image:

| Image | CRITICAL | HIGH | Breakdown |
|---|---:|---:|---|
| `almir/webhook:latest` (baseline) | 2 | 37 | `stdlib` 22 (legacy Go toolchain, e.g. CVE-2026-25679, CVE-2026-32280), `libssl3`/`libcrypto3` 14 (incl. **CVE-2026-31789** ×2 CRITICAL), musl 2, zlib 1 |
| `localobserve-webhook:latest` (rebuilt) | 0 | 0 | Compiled from source with Go 1.27.1 (`CGO_ENABLED=0`) at commit `2bbdeb9f90b5` on digest-pinned Alpine 3.24 (`apk upgrade` at build time) |

**Result: 39 → 0 fixable HIGH/CRITICAL findings.** The rebuild lives in
`alerts/webhook/Dockerfile`; CI now builds and scans the image in
`.github/workflows/container-image-scan.yml`, and `scripts/scan-images.sh` includes it.

### ⚠️ `clamav/clamav` latest + `:latest_base` (1 HIGH each, 0 CRITICAL) — Digest-pinned 2026-10-04, #111

| CVE | Library | Notes |
|---|---|---|
| CVE-2026-103111 | pcre2 | Out-of-bounds write via crafted regex; 10.48-r0 → fixed 10.49-r0 in Alpine feed, image rebuild pending |

These services ran floating `:latest` tags after this document's September baseline
(then 0 HIGH). Trivy CI flagged pcre2 on 2026-10-04 — a pure drift event with no repo
change. Both are now pinned to their 2026-10-04 digests so the baseline cannot move
silently; the finding is intentionally **not** suppressed in `.trivyignore` so the
re-pin signal stays visible (ClamAV rebuilds frequently). Virus-database freshness
is unaffected by the image pin — CVDs update at runtime.

### 🟡 `nvcr.io/nvidia/k8s/dcgm-exporter` (34 HIGH) — Upstream rebuild required

Top packages: `stdlib` (27), `google.golang.org/grpc` (3), `libssl3t64` (1), `openssl-provider-fips` (1), `golang.org/x/crypto` (1), `golang.org/x/text` (1). Gated under `gpu` profile.

### 🟡 `netsampler/goflow2` (30 HIGH) — Upstream rebuild required

Top packages: `golang.org/x/crypto` (10), `stdlib` (10), `golang.org/x/net` (5), `libcrypto3` + `libssl3` (4), `golang.org/x/text` (1). Gated under `netflow` profile.

## Recommendations

1. **Keep image tags pinned** — the pinned-digest images (`falco`, `openobserve`, `otel-collector-contrib`) can acquire CVEs as the Trivy DB moves on. Re-scan weekly via the workflow. Findings that are upstream-waiting are suppressed per-CVE with a tracked reason and review date in `.trivyignore` (see issues #82/#83/#84/#87); entries must never be added without a tracking issue.
2. **Maintain runtime detection** — even with patched images, Go stdlib CVEs in auxiliary containers (`dcgm-exporter`, `goflow2`, `grype`) are mostly unfixed until upstream rebuilds with Go ≥1.26.6 + x/crypto ≥0.52. Falcosidekick + custom Falco rules catch exploitation at the syscall level, providing defense-in-depth.
3. **Re-pin when upstream rebuilds land.** The workflow (`.github/workflows/container-image-scan.yml`) and Renovate config (`renovate.json`) are designed to surface these automatically.

## Reproducing the Scan

```bash
# Local Docker-managed Trivy (preferred — DB cached locally)
docker run --rm -v $HOME/.cache/trivy:/root/.cache/trivy aquasec/trivy:latest image \
  --severity HIGH,CRITICAL \
  --format table \
  <image>:<tag>

# Or run all in one go via the helper script
./scripts/scan-images.sh
```
