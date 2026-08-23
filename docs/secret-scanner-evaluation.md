# Secret Scanner Evaluation (Issue #58)

**Goal:** Evaluate candidate secret-scanning tools and recommend an integration
path for the LocalObserve pipeline. This is an *evaluation* (not a permanent
service); the deliverable is a decision + a lightweight PoC wired into the repo.

## Candidates

| Tool | Repo | Model | Strengths | Weaknesses | Fit |
|------|------|-------|-----------|------------|-----|
| **betterleaks** | [betterleaks/betterleaks](https://github.com/betterleaks/betterleaks) | ML-assisted heuristics + rules (gitleaks-compatible) | Fewer false positives via ML, fast, offline, reads `.gitleaks.toml` configs | Newer project, smaller community | **Primary (chosen)** |
| **gitleaks** | [gitleaks/gitleaks](https://github.com/gitleaks/gitleaks) | regex + entropy, rules (toml) | Fast, mature, huge rule set, easy CI/pre-commit, no network | Can miss semantic/context secrets | Alternative |
| **trufflehog** | [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | regex + verification (live cred check) | Verifies secrets against live providers, deep history scan | Slower, network egress, larger binary | History/deep |
| **ripsecrets** | [sirwart/ripsecrets](https://github.com/sirwart/ripsecrets) | YARA-adjacent patterns | Tiny, fast pre-commit | Narrower coverage | Optional |
| **kingfisher** | [mongodb/kingfisher](https://github.com/mongodb/kingfisher) | YARA rules for secrets | Reuses YARA infra (pairs with ClamAV) | Focused on specific formats | Optional |
| **GitGuardian ggshield** | [GitGuardian/ggshield](https://github.com/GitGuardian/ggshield) | SaaS-backed detection | Best-in-class accuracy, dashboard | Requires API key / external SaaS | Opt-in |

## Benchmark methodology

The `gitleaks` project publishes a [benchmark](https://github.com/gitleaks/gitleaks#benchmarks)
repo (`gitleaks-benchmark`) comparing detection rate and speed across tools on
a curated corpus of true/false secrets. Recommended local procedure:

```bash
# 1. Clone the benchmark corpus
git clone https://github.com/gitleaks/gitleaks-benchmark /tmp/gitleaks-benchmark
# 2. Run each candidate over the same corpus and capture findings + wall time
gitleaks detect -s /tmp/gitleaks-benchmark --report-format json -r /tmp/gitleaks.json
trufflehog filesystem /tmp/gitleaks-benchmark --json > /tmp/trufflehog.json
# 3. Compare true-positive rate, false-positive rate, and scan duration.
```

Capture the numbers in this doc when executed; they are environment-specific and
are intentionally **not** committed as fixed values.

## Recommendation

1. **Primary: `betterleaks`** for pre-commit hooks and CI (`task secret-scan`).
   It is fast, offline, ML-assisted (fewer false positives than pure-regex
   scanners), and — being gitleaks-compatible — reuses the same `.toml` rule
   format the ecosystem already understands. Installed through mise
   (`betterleaks = "1.8.1"` in `mise.toml`); the command is
   `betterleaks dir --config .betterleaks.toml --redact .`.
2. **Deep/historical: `trufflehog`** for periodic full-history scans
   (`trufflehog git --branch=main --only-verified`) — optional, run in CI, may
   require network egress allow-listing.
3. **Other tools** (gitleaks, ripsecrets, kingfisher, ggshield): evaluated as
   optional alternatives; betterleaks is the default.

### Why not a runtime service?

Secret scanning is a *source/CI* control, not a host-runtime telemetry stream.
Shipping it as a container in the detection pipeline would duplicate pre-commit/CI
coverage and add noise. The OTEL pipeline stays focused on runtime threats.

## PoC status

- [x] `betterleaks` added to `mise.toml` and installed/verified.
- [x] `.betterleaks.toml` committed (gitleaks-compatible rules + allowlist for test fixtures).
- [x] `task secret-scan` added to `Taskfile.yml` using `betterleaks dir`.
- [ ] Benchmark numbers captured (run the methodology above locally).
- [ ] Optional `trufflehog` CI job (deferred; needs egress approval).
