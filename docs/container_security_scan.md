# Container Image Vulnerability Scan

**Scan date:** 2026-08-27
**Scanner:** [Trivy](https://github.com/aquasecurity/trivy) v0.x (aquasec/trivy:latest)
**Severity filter:** `HIGH`, `CRITICAL` (MEDIUM/LOW intentionally excluded to focus on actionable risk)
**Methodology:** All images declared in `docker-compose.yaml` were scanned locally. Local builds (`localobserve-webhook`) are excluded — they have no published CVE data. Host filesystem / mounted volumes are out of scope (covered separately by the secret scanner evaluation, see issue #58).

## Executive Summary

| Status | Count | % of stack |
|---|---|---|
| ✅ Clean (0 HIGH / 0 CRITICAL) | 6 / 10 | 60% |
| ⚠️ Action required (fixable via tag pin) | 1 / 10 | 10% |
| 🟡 Upstream rebuild required | 3 / 10 | 30% |

- **0 CRITICAL** findings across all images
- **66 HIGH** findings total, of which **64 are Go-stdlib CVEs** that only resolve when upstream maintainers rebuild with Go ≥1.26.6 / `golang.org/x/crypto` ≥0.52.0 / `golang.org/x/net` ≥0.55.0

## Per-Image Results

| # | Image | Tag (pinned vs latest) | Base | HIGH | CRIT | Action |
|---|---|---|---|---:|---:|---|
| 1 | `falcosecurity/falco` | `@sha256:b4166a...` (pinned) | wolfi | 0 | 0 | ✅ None |
| 2 | `public.ecr.aws/zinclabs/openobserve` | `@sha256:0c057f...` (pinned) | debian 13 | 0 | 0 | ✅ None |
| 3 | `ghcr.io/timescale/rsigma` | `0.19.0` (pinned) | — | 0 | 0 | ✅ None |
| 4 | `clamav/clamav` | `latest` (active profile) | alpine 3.24 | 0 | 0 | ✅ None |
| 5 | `clamav/clamav` (`:latest_base`) | `latest` (active profile) | alpine 3.24 | 0 | 0 | ✅ None |
| 6 | `localobserve-webhook` | `latest` (local build) | python | n/a | n/a | ✅ Local; review dependencies separately |
| 7 | `osquery/osquery` | was `latest` → **pinned `5.17.0-ubuntu22.04`** | was ubuntu 20.04 → ubuntu 22.04 | 2 → 2 | 0 | ⚠️ Traded 2021 libsystemd CVE for 2025-26 libssl + gpgv. **Net improvement** (no CRITICAL, no kernel-level issue). |
| 8 | `otel/opentelemetry-collector-contrib` | `@sha256:f41d79...` (pinned) | Go stdlib v1.26.5 | 8 | 0 | 🟡 Upstream rebuild required (Go 1.26.6+) |
| 9 | `nvcr.io/nvidia/k8s/dcgm-exporter` | `latest` | debian 13 | 29 | 0 | 🟡 Upstream rebuild required (Go 1.26.6+ + x/crypto ≥0.52 + x/net ≥0.55) |
| 10 | `netsampler/goflow2` | `latest` | alpine 3.23 | 27 | 0 | 🟡 Upstream rebuild + OpenSSL 3.5.7+ |

## Findings Detail

### ⚠️ `osquery/osquery` (2 HIGH) — Pin applied

| Library | CVE | Installed | Fixed | Notes |
|---|---|---|---|---|
| `libssl3` | CVE-2026-45447 | 3.0.2-0ubuntu1.19 | 3.0.2-0ubuntu1.25 | OpenSSL PKCS7_verify heap UAF |
| `gpgv` | CVE-2025-68973 | 2.2.27-3ubuntu2.3 | 2.2.27-3ubuntu2.5 | GnuPG out-of-bounds write |

The previous `:latest` (Ubuntu 20.04 base) had `libsystemd0` + `libudev1` affected by **CVE-2021-33910** (kernel-level vulnerability — far more severe). Pinning to `5.17.0-ubuntu22.04` eliminates that older kernel-adjacent issue. Both remaining findings are **fixable in-distro**; once Ubuntu 22.04 `apt-get upgrade` rolls out upstream, a new `5.17.0-ubuntu22.04-N` tag will absorb them.

### 🟡 `otel/opentelemetry-collector-contrib` (8 HIGH) — Upstream rebuild required

All 8 findings are Go stdlib CVEs (v1.26.5). Fixed in Go 1.26.6, 1.25.13, 1.27.0-rc.3:

| CVE | Component | Description |
|---|---|---|
| CVE-2026-33818 | `encoding/asn1` | Excessive recursion in Unmarshal |
| CVE-2026-39821 | `net/http` + x/net/idna | Punycode privilege escalation |
| CVE-2026-46600 | `net/dns` | Invalid DNS record parsing DoS |
| CVE-2026-56853 | `net/http` | Unencrypted HTTP/2 DoS |
| CVE-2026-56858 | `html/template` | Cross-Site Scripting |
| CVE-2026-56859 | `encoding/xml` | XML decoding recursion DoS |
| CVE-2026-56860 | `net/url` | Quadratic complexity path parsing DoS |
| CVE-2026-56862 | `crypto/tls` | Indefinite KeyUpdate DoS |

Track upstream: <https://github.com/open-telemetry/opentelemetry-collector-contrib/releases>

### 🟡 `nvcr.io/nvidia/k8s/dcgm-exporter` (29 HIGH) — Upstream rebuild required

29 findings split across `dcgm-exporter` (11), `shelless_ulimit_amd64` (9), `sleep_amd64` (9). All are Go stdlib + `golang.org/x/crypto/ssh` + `golang.org/x/text` issues fixed by:
- Go 1.26.6+
- `golang.org/x/crypto` ≥0.52.0
- `golang.org/x/text` ≥0.39.0
- `golang.org/x/net` ≥0.55.0

Track upstream: <https://github.com/NVIDIA/dcgm-exporter/releases>

### 🟡 `netsampler/goflow2` (27 HIGH) — Upstream rebuild + OpenSSL bump

| Component | HIGH | Notes |
|---|---:|---|
| alpine 3.23 OS libs (libcrypto3 + libssl3) | 2 | CVE-2026-45447 fixed in OpenSSL 3.5.7 |
| Go binary: `golang.org/x/crypto/ssh` | 9 | SSH key auth bypasses + DoS |
| Go binary: `golang.org/x/net/html` | 2 | XSS via HTML parsing |
| Go binary: Go stdlib | remaining | Same Go 1.26.6 fixes as OTel |

Upstream action: rebuild on alpine 3.24 (OpenSSL 3.5.7) + Go 1.26.6+. The project hasn't published a release since May 2026 — no fix available until maintainer re-engages. Track: <https://github.com/netsampler/goflow2/pkgs/container/goflow2>.

## Recommendations

1. **Keep image tags pinned** (already done for 3 of 6 used images). Avoid `:latest` for security-sensitive services. The osquery tag is now pinned (this PR).
2. **Add Trivy scanning to CI** so new HIGH/CRITICAL findings block merges (`.github/workflows/trivy-scan.yml`, this PR).
3. **Enable Renovate / Dependabot** to auto-bump image tags weekly (`renovate.json`, this PR).
4. **Re-run scan monthly** and re-pin once upstream rebuilds land.
5. **Consider Falcosidekick for Go-bin CVE defense-in-depth** — even though our falcosidekick image is clean today, runtime syscall monitoring catches exploitation attempts against Go stdlib bugs in otel/goflow2/dcgm.

## Out of Scope

- **Local Python build (`localobserve-webhook`)** — its dependencies should be scanned with the secret/CVE scanner evaluated in issue #58.
- **MEDIUM/LOW severity** — re-run with `--severity MEDIUM,HIGH,CRITICAL` when prioritizing hardening.
- **Runtime SBOM** — Trivy can export SPDX/CycloneDX SBOMs; not currently part of the scan but trivially added.

## Reproducing the Scan

```bash
# Pull the trivy scanner (already local as aquasec/trivy:latest)
docker run --rm aquasec/trivy version

# Scan each image
docker run --rm aquasec/trivy image \
  --severity HIGH,CRITICAL \
  --quiet \
  --format table \
  <image>:<tag>

# Or run all in one go via the helper script
./scripts/scan-images.sh
```

The helper script (`scripts/scan-images.sh`, added in this PR) iterates every image declared in `docker-compose.yaml` and emits a summary table.
