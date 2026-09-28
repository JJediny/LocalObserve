# Benchmark, Refactoring & AI-Agent Observability Plan

Status: **approved for implementation** (2026-09-27)
Inputs: open issues #82–#89, #91; merged PRs #59–#90; current branch `feature/container-image-security`
Related: closes #91; de-risks #82–#89; supersedes the Loki-era notes in `docs/optimization-refactoring.md`

---

## 0. Review summary (what we heard from issues & PRs)

### Open issues
| # | Topic | Relevance to this plan |
|---|---|---|
| #91 | OTEL Agent Monitoring with RSigma rules — capture tool calls & permissions on opencode/pi harness sessions | **Directly implemented** in Part B (agent session capture + Sigma rules + dashboard) |
| #82 | Tracking: 86 HIGH CVEs on upstream vendor images | Runtime budget work (Part A) documents a per-image "accept or pin" gate; benchmark harness measures cost of replacements |
| #83–#86 | dcgm-exporter (34), goflow2 (30), grype (15), falco (3) HIGHs | goflow2 runs by default today and writes a JSONL file continuously — gating it behind a profile is both a CVE- and an I/O-win |
| #87–#89 | osquery (2), otel-contrib (1), openobserve (1) HIGHs | Pinned digests stay; `.trivyignore` documentation path already agreed in #82 |

### Recently merged PRs (context)
- #76/#81: image scanning + digest pinning — the compose file now uses pinned digests; `scripts/scan-images.sh` exists.
- #78: self-authored images released from SemVer tags — enables us to ship a tiny "agent-session shipper" image later without new infra.
- #80/#79/#77: CI hardening — the caldera job no longer force-pushes lockfiles.
- #66: rsigma healthcheck + alert webhook validation — the webhook path we extend in Part B is already tested.
- Current branch `feature/container-image-security` (1 commit ahead of `main`) overlaps merged PR #76; **reconcile before starting** (rebase or drop).

### Findings that motivated this plan (measured in-repo)
1. **The SSD-optimized osquery profile is not the one being run.** `docker-compose.yaml` mounts `./osqueryd.conf` (FIM + KEV queries every 300 s, 30+ scheduled queries) while `osqueryd-ssd-optimized.conf` (hourly/daily intervals) sits unused. Current `.data/osquery` = **158 MB**.
2. **No log rotation anywhere.** `./.data/osquery/osqueryd.results.log` and `./.data/falco/events.jsonl` grow unbounded on the SSD.
3. **Falco double-writes**: `file_output` **and** `stdout_output` are both enabled → every event hits the bind-mounted file *and* Docker's `json-file` log (also unbounded; no `logging:` caps in compose).
4. **Stale 385 MB** of legacy OpenObserve WAL/parquet at `.data/openobserve` (only referenced by the archived Loki script `archive/start-loki.sh`); the live mount is `.data/openobserve-data` (102 MB).
5. **rsigma is underused**: 1 active rule (`suspicious_unshare.yaml`) despite a curation engine (`rules/sigma/manage_rules.py`, `curated_rules.yaml`). Detection capability is cheap to add here (RAM-bounded at 128 MB, no extra disk).
6. **No runtime benchmark exists** — only the OpenObserve *base-image* benchmark (`tests/benchmark_base_images/`). Nothing measures stack-wide SSD writes or RAM, so every tuning claim is unverifiable.
7. **Metrics pipeline ships to the `debug` exporter** (`otel-collector-config.yaml` metrics pipeline) — pure overhead in production.
8. **Agent telemetry already has a paved road**: `.env` has OTLP endpoint vars, the collector has OTLP receivers + a traces pipeline, and Traces dashboards exist — but there is no agent stream, no agent Sigma rules, no session dashboard, and no privacy controls (prompts/completions land in storage verbatim).

---

## Goals

1. **Benchmark first, tune second**: a reproducible harness that measures per-service RAM, per-service SSD writes, log-growth rates and detection latency, with regression budgets enforced by pytest.
2. **Cut SSD wear and RAM floor measurably** (targets: ≥ 60% reduction in steady-state stack write rate; stack idle RSS within declared budgets).
3. **Increase detection & alerting while at it**: expand rsigma active rules, add AI-agent behavior detections, add agent-session alerts and an out-of-the-gate dashboard.
4. **Zero-secret-by-default for agent capture**: prompts/completions are redacted at the collector unless explicitly enabled.

Non-goals: replacing OpenObserve; renaturing the Loki archive; fixing upstream image CVEs (tracked in #82–#89); GPU profile work.

---

## Part A — Benchmark & resource-impact workstream

### A0. Measured baseline (2026-09-27, first harness runs)
Live measurements from the running stack (default docker context, 90s idle window, after the logging-caps/falco/goflow2 changes):

| Service | Max RAM (MiB) | Writes (MiB/min) | Budget |
|---|---:|---:|---|
| openobserve | 502–520 | **2.9–4.3 (steady)** | 5.0 |
| otel-collector | 154 | 0.0 | 1.0 |
| alert-receiver | 15 | 0.0 | n/a |
| goflow2 (profile-gated) | 7 | 0.0 | n/a |

**Key SSD finding**: OpenObserve writes ~3–4 MiB/min *even when idle*, even after the self-scrape interval went 15s→30s. Root cause: the `openobserve-internals` scrape feeds ~90 `zo_*` metric streams (including histogram buckets), so every scrape cycle produces parquet writes across ~90 streams. Next tuning pass (tracked below): drop histogram-bucket streams at the collector, move the scrape to 60s, or apply stream-level retention to metric streams. This is the single biggest steady-state SSD lever discovered by the harness — exactly what it exists for.

### A1. Benchmark harness (new)
`tools/bench_stack.py` (uv script, no new hard deps — stdlib + docker CLI):

- **Sampling loop** (default 10 s interval): `docker stats --no-stream` per service (CPU %, MemUsage), cgroup v2 `io.stat` per container (bytes read/written), `du` delta on `./.data/*` and `/var/lib/docker/containers` log growth.
- **Scenarios** (flags): `--scenario idle|attack|agent|scan`
  - `idle`: 30 min steady-state (default budgets below)
  - `attack`: runs `./event-generator` + one safe CALDERA ability via existing harness, measures detection latency (syscall → OpenObserve searchable → alert-receiver webhook receipt)
  - `agent`: runs `tools/agent_session_demo.py` (Part B) and measures marginal RAM/SSD cost per session
  - `scan`: ClamAV profile daily sweep (informational; exempt from idle budgets)
- **Artifacts**: `.artifacts/bench/<run-id>/samples.csv`, `summary.json`, `summary.md` (human table).
- **Comparison**: `tools/bench_compare.py` (latest run vs. baseline) emits a markdown delta report; used to prove SSD/RAM reduction claims.

Budgets (recorded in `tools/bench_budgets.json`, enforced by tests — measured *after* tuning):

| Service | RAM budget (steady RSS) | Write budget (idle) |
|---|---|---|
| openobserve | ≤ 700 MB | ≤ 2 MB/min |
| otel-collector | ≤ 260 MB | ≤ 1 MB/min |
| falco | ≤ 320 MB | ≤ 0.5 MB/min |
| osquery | ≤ 160 MB | ≤ 1.5 MB/min |
| rsigma | ≤ 128 MB (compose cap) | n/a |
| alert-receiver | ≤ 40 MB | n/a |
| **Stack total** | **≤ 1.6 GB** | **≤ 5 MB/min** |

Detection latency SLO (attack scenario): Falco event → OpenObserve searchable ≤ 30 s; OpenObserve/rsigma alert → alert-receiver ≤ 60 s.

### A2. SSD impact fixes (ranked by expected win)
1. **Log rotation** — `scripts/logrotate-localobserve.conf` (weekly, rotate 8, compress, copytruncate for the two OTel-tailed files) + `task rotate-logs` + install step documented in README. OTel `file_log` keeps tailing across copytruncate via inode fallback (verify in harness).
2. **Docker log caps** — `logging: {driver: json-file, options: {max-size: "10m", max-file: "3"}}` on every always-on service (falco, osquery, openobserve, otel-collector, rsigma, alert-receiver, goflow2).
3. **Falco single-sink** — `stdout_output.enabled: false` (keep `file_output` only). Docker journald/json-file no longer receives a duplicate of every syscall event.
4. **osquery profile selection** — compose volume becomes `-${OSQUERY_CONFIG:-osqueryd.conf}:/etc/osquery/osquery.conf:ro`; `.env` documents `osqueryd-ssd-optimized.conf` as the low-impact choice and `osqueryd-deep-forensic.conf` as the on-demand one. Default stays `osqueryd.conf` (balanced); the harness quantifies the delta.
5. **goflow2 behind a profile** — it is only useful when a flow exporter exists; gate it with `profiles: [netflow]` (also removes 30 HIGH CVEs from the default attack surface, refs #84).
6. **Metrics pipeline hygiene** — remove `debug` exporter from the metrics pipeline; `openobserve-internals` scrape 15 s → 30 s.
7. **Stale data removal** — document/execute removal of legacy `.data/openobserve` (385 MB) in README troubleshooting (data, not code).
8. **OpenObserve retention** — keep `ZO_RETENTION_PERIOD=180` (compliance crosswalk workstream); instead audit `ZO_MEMORY_CACHE_*` / compaction knobs against measured RSS in A1 and record findings in `docs/benchmarks.md` appendix.

### A3. RAM impact fixes
- Keep all `mem_limit`s; the harness now verifies steady RSS stays ≤ 75% of each limit (headroom for spikes).
- Collector `memory_limiter` stays at 256 MiB (compose ceiling 512 MB is 2×; correct back-pressure geometry, keep).
- rsigma rule expansion (A4) must fit the existing 128 MB limit — the harness's `agent`/`attack` scenarios assert it.

### A4. Detection & alerting increases (net-positive while SSD/RAM shrink)
- **rsigma active ruleset expansion** (RAM-cheap, disk-free): promote a focused set from the curation engine into `rules/sigma/active_rules/` covering Linux persistence/execution gaps the Falco set doesn't already cover (credential files, sudoers tampering, systemd unit drops in user paths, reverse-shell one-liners, kernel module tooling). Each rule: MITRE tags, `falsepositives`, and a matching entry in the detection-coverage test.
- **AI-agent detections** (Part B5) — new logsource `product: ai_agent`, evaluated on the existing rsigma daemon.
- **Alerts**: two new OpenObserve alerts (agent sensitive-file write, agent error spike) — see B6.
- **Detection latency** becomes a tested SLO rather than folklore (A1 attack scenario).
- **Coverage matrix**: extend `tests/test_detection_coverage.py` to enumerate active Sigma rules so coverage claims stay honest as the ruleset grows.

---

## Part B — AI agent session capture (issue #91)

### B1. Data model & conventions
- A **session** = one OTLP trace (W3C `trace_id`). Tool calls = child spans.
- Resource attributes (set by the shipper, standardized in `docs/ai_agent_observability.md`):
  - `service.name` = agent app (e.g. `opencode`, `pi-harness`, `agent-demo`)
  - `service.namespace` = `ai-agents` ← the routing key
  - `ai.session.id`, `ai.agent.name`, `ai.workspace.root`
  - GenAI semconv where available: `gen_ai.tool.name`, `gen_ai.request.model`, `gen_ai.usage.*`
- **Streams**: traces → existing `default` (traces stream, already dashboarded); agent **logs** → new `agent-logs` log stream; rsigma detections unchanged (webhook → alert-receiver).
- **Privacy**: default-on redaction processor deletes `gen_ai.prompt`, `gen_ai.completion`, `llm.*` attributes at the collector; `AGENT_CAPTURE_PROMPTS=true` (env) disables redaction for local debugging only.

### B2. OTel collector wiring (`otel-collector-config.yaml`)
- New processors:
  - `resource/ai_agent` — upsert `service.namespace=ai-agents` routing tag + `log.sink=openobserve`.
  - `transform/agent_redact` — OTTL `delete_key` for prompt/completion attributes unless `AGENT_CAPTURE_PROMPTS=true`.
  - `filter/ai_agent_keep` / `filter/ai_agent_drop` — split the shared `otlp` logs receiver into two pipelines: `logs/ai_agent` (namespace matches, exports to `agent-logs` stream **and** rsigma) and `logs/otlp` (everything else, unchanged).
- Traces pipeline unchanged except adding `resource/ai_agent` so agent spans are identifiable in the traces stream.

### B3. Logfire out-of-the-gate (Python)
- Add `logfire` to the dev dependency group (Logfire speaks plain OTLP; when `send_to_logfire=False` it honors the existing `.env` OTLP endpoint vars — no Logfire account needed).
- `tools/agent_otel_prelude.py` — importable one-liner for any Python agent/harness:
  ```python
  import agent_otel_prelude  # configures logfire→OTLP, session attrs, instrumentation
  ```
  It sets resource attrs (`service.namespace=ai-agents`, session id), and auto-instruments OpenAI/Anthropic clients + pydantic-ai when present.
- `.env` additions: `OTEL_EXPORTER_OTLP_ENDPOINT_HTTP` guidance (Logfire prefers HTTP/protobuf on 4318), `AGENT_CAPTURE_PROMPTS=false`, `AI_SESSION_NAMESPACE=ai-agents`.
- opencode/pi wiring documented in B8: point the agent's OTLP exporter at `http://localhost:4318` (or 4317 for gRPC); any OTLP-speaking agent works with zero further changes. (Exact opencode config key is version-dependent — documented with a version check, not hard-coded.)

### B4. Synthetic demo / conformance session
`tools/agent_session_demo.py` — runs a scripted "agent session" that performs: a benign tool call (read file in workspace), a shell tool call, a **sensitive-file access attempt** (`/etc/shadow`), and a **credential-file read** (`.env`) — each as an OTLP span+log. Doubles as: (a) Part A `agent` benchmark workload, (b) the fixture for e2e tests, (c) a live example for docs.

### B5. rsigma Sigma rules for agents (`rules/sigma/active_rules/`)
Logsource `product: ai_agent, service: otel` + a pipeline field mapping (`gen_ai.tool.*` → `CommandLine`/`Image` equivalents so existing detection idioms carry over):

| Rule | Level | MITRE |
|---|---|---|
| AI Agent Dangerous Shell Command | high | T1059, T1561.002 |
| AI Agent Sensitive File Access | high | T1003, T1552.001 |
| AI Agent Credential File Read | critical | T1552.001/.004 |
| AI Agent Workspace Escape Attempt | medium | T1083 |
| AI Agent Suspicious Network Egress | medium | T1071 |

All wired to the existing `webhooks/alert_receiver.yaml` destination (severity already flows through).

### B6. OpenObserve alerts (added to `alerts/openobserve/alerts.json`)
- `AIAgent-Sensitive-File-Access` (stream `agent-logs`, ≥ 1 hit / 1 min, severity-critical template) 
- `AIAgent-Tool-Error-Spike` (error-rate heuristic on `agent-logs`, 5+ errors / 5 min).

### B7. Dashboard: `dashboards/openobserve/AI_Agent_Sessions.json`
New tab-based dashboard (same schema as `Osquery_Events.json`), variables `$service` (query_values on traces `service_name`) and `$session` (agent-logs `ai_session_id`):

| Panel | Type | Stream | Query (SQL) |
|---|---|---|---|
| Sessions over time | area | traces | `histogram(_timestamp), count(service_name) FROM "default" WHERE service_namespace='ai-agents' GROUP BY x` |
| Tool calls by name | pie | agent-logs | `gen_ai_tool_name, count(*) GROUP BY 1` |
| Errors by service | bar | traces | `WHERE span_status='ERROR'` |
| Session duration (avg/max ms) | metric | traces | `avg(duration), max(duration)` |
| Security events (rsigma hits) | table | agent-logs | filtered to detection markers |
| Recent agent events | table | agent-logs | latest 100 rows |

Imported with the existing `task sync-oo-import`.

### B8. Docs & tests
- `docs/ai_agent_observability.md` — conventions, shipper setup (Logfire / opencode / generic OTLP), privacy modes, verification steps.
- `tests/test_agent_observability.py` (static): collector config parses; processors/exporters referenced by pipelines exist; `filter` conditions syntactically valid; Sigma rules parse + unique IDs + required keys; dashboard/alert JSON valid; budgets file valid.
- `tests/test_agent_session_e2e.py` (integration, `--run-stack`): runs the demo, then asserts within SLO: spans in traces stream, logs in `agent-logs`, detection webhook received, **and** redaction actually removed prompt content.

---

## Part C — Delivery sequence (PR-sized)

| # | Slice | Files touched | Closes/refs |
|---|---|---|---|
| 0 | Reconcile `feature/container-image-security` with `main` (rebase or drop) | — | #76 overlap |
| 1 | Benchmark harness + budgets + compare tool + Taskfile | `tools/bench_stack.py`, `tools/bench_compare.py`, `tools/bench_budgets.json`, `Taskfile.yml`, `tests/test_benchmarks.py` | A1 |
| 2 | SSD fixes: rotation, docker log caps, falco stdout-off, goflow2 profile | `docker-compose.yaml`, `falco-config.yaml`, `scripts/logrotate-localobserve.conf` | A2 |
| 3 | osquery profile selection + docs | `docker-compose.yaml`, `.env.example`-style docs in README | A2.4 |
| 4 | Collector: split agent pipeline, redaction, metrics hygiene | `otel-collector-config.yaml` | B2 |
| 5 | Agent shipper: logfire prelude + demo + e2e tests | `tools/agent_otel_prelude.py`, `tools/agent_session_demo.py`, `pyproject.toml`, tests | B3/B4, #91 |
| 6 | Sigma rules (agent + Linux promotion) + coverage tests | `rules/sigma/**`, tests | B5, A4 |
| 7 | Alerts + dashboard + docs | `alerts/openobserve/alerts.json`, `dashboards/openobserve/AI_Agent_Sessions.json`, `docs/ai_agent_observability.md` | B6/B7/B8, #91 |

Slices 1–3 are pure-debt paydown and can merge independently. Slices 4–7 form the agent feature (#91) and land in order.

### Acceptance criteria (whole plan)
- `task bench --scenario idle` produces a summary within all budgets above; report checked into `docs/reports/`.
- Before/after `bench_compare` shows ≥ 60% idle write-rate reduction vs. pre-fix baseline.
- `task test` green (static suite), `task test-host-emulation` green, agent e2e green under `--run-stack`.
- A synthetic agent session triggers at least 2 Sigma detections and ≥ 1 OpenObserve alert, with prompts redacted in storage by default.
- #91 closeable: tool calls, permissions/session metadata and detections visible in one dashboard.

### Risks
- **copytruncate + OTel file_log** could briefly miss lines at rotation → harness asserts no detection loss across a forced rotation; fall back to `logrotate` with `create` if observed.
- **Stream name for traces** (`default`) means agent traces share the generic traces stream — acceptable (distinguished by `service_namespace`), avoids a second exporter.
- **opencode config drift** (OTLP env names vary by version) → doc includes a per-version check; any OTLP-speaking agent works regardless.
- **OpenObserve alert on a derived stream** (`agent-logs`) must exist before alerts import → import order documented (collector creates stream on first log; `sync-oo-import` already idempotent).
