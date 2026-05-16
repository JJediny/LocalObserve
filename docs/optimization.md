## DISK_OPTIMIZATION.md

# Disk Optimization Guide

This document summarizes the disk- and noise-reduction changes that were applied to the current repo so the Loki stack remains usable during evaluation runs.

## Goals

The current tuning aims to:
- reduce unnecessary host and container disk writes
- reduce alert noise from known desktop false positives
- avoid bursty osquery scheduling
- make Docker bind mounts reliable on this host
- make image selection reproducible for benchmarking

## Applied changes

### 1. Repo-local osquery log path

**Why:**
The original host path `/var/log/osquery` was not reliably visible inside containers in this environment.

**What changed:**
- osquery logs are now written to `./.data/osquery`
- Alloy reads `./.data/osquery` via a bind mount
- the OTel Collector comparison profile reads the same file

**Files:**
- `docker-compose.yaml`
- `osqueryd.conf`
- `osqueryd-ssd-optimized.conf`
- `setup-osqueryd.sh`

**Impact:**
- avoids duplicate troubleshooting restarts caused by an empty bind mount
- keeps the ingest file in a single repo-local location that is easy to inspect and rotate

## 2. osquery config cleanup

**Why:**
The installed `osqueryd` in this environment treated several JSON options as invalid or CLI-only.

**What changed:**
- removed invalid JSON options from `osqueryd.conf`
- removed invalid JSON options from `osqueryd-ssd-optimized.conf`
- added `osquery.flags` for CLI-only plugin settings:
  - `--config_plugin=filesystem`
  - `--logger_plugin=filesystem`
- updated `setup-osqueryd.sh` to install both:
  - `/etc/osquery/osquery.conf`
  - `/etc/osquery/osquery.flags`

**Impact:**
- eliminates invalid-flag warnings during config validation
- keeps the service config cleaner and closer to what the local binary actually supports

## 3. osquery scheduler smoothing

**Why:**
A low splay value causes more scheduled queries to execute in tighter bursts, which can create short I/O spikes.

**What changed:**
- increased `schedule_splay_percent` from `10` to `25`

**Files:**
- `osqueryd.conf`
- `osqueryd-ssd-optimized.conf`

**Impact:**
- spreads query execution more evenly across time
- reduces bursty writes into `osqueryd.results.log`

## 4. Falco output tuning

**Why:**
Falco can generate substantial log volume on a desktop-style Linux host if left near its defaults or if custom overrides are not actually loaded.

**What changed:**
- ensured the repo override is mounted into `/etc/falco/config.d/zz-local.yaml`
- enabled `buffered_outputs: true`
- set `priority: warning`
- kept `file_output` disabled
- kept `syslog_output` disabled
- used HTTP output to `falcosidekick`

**Files:**
- `docker-compose.yaml`
- `falco-config.yaml`

**Impact:**
- reduces Falco write amplification
- reduces low-value diagnostic noise in the active eval path

## 5. Falco false-positive suppression for desktop workloads

**Why:**
This host showed expected desktop/GUI helper behavior that created noisy Falco alerts without adding much security value for this evaluation.

**What changed:**
### Crashpad ptrace noise
Added a local extension to `known_ptrace_binaries` for:
- `chrome_crashpad`
- `chrome_crashpad_handler`

### Desktop auth helper sensitive-file noise
Added a targeted exception to `user_read_sensitive_file_conditions` for:
- `systemd-executor`
- `cinnamon-screensaver-pam-helper`

only when they read:
- `/etc/shadow`
- `/etc/pam.d/*`

**Files:**
- `falco_rules.local.yaml`

**Impact:**
- reduces repeated desktop false positives
- preserves a narrow exception scope instead of broadly ignoring sensitive-file activity

## 6. Internal-only service exposure where possible

**Why:**
Publishing extra host ports increases process churn, collision risk, and operational noise without helping local evaluation.

**What changed:**
- Loki `read`, `write`, and `backend` use internal exposure instead of published host ports
- `falcosidekick` no longer publishes `2801` to the host
- `gateway` remains the main Loki entrypoint on `3100`
- MinIO is pinned to stable ports `9000` and `9001`

**Files:**
- `docker-compose.yaml`

**Impact:**
- fewer port conflicts
- fewer unnecessary host listeners
- simpler compose lifecycle during repeated benchmark runs

## 7. Pinned eval images

**Why:**
Using `latest` makes repeatable comparisons harder because behavior can drift between runs.

**What changed:**
Pinned these services to exact digests:
- Loki (`read`, `write`, `backend`)
- Grafana
- Alloy
- Falco
- Falcosidekick
- OpenObserve
- OTel Collector Contrib

**Files:**
- `docker-compose.yaml`

**Impact:**
- more reproducible evaluation runs
- easier to compare before/after tuning results

## Host steps required after these changes

To apply the osquery changes to the installed host service:
1. run `sudo ./setup-osqueryd.sh configure`
2. run `sudo systemctl restart osqueryd`

## Validated outcomes

The repo changes were validated to the extent possible from this environment:
- Alloy tails `./.data/osquery/osqueryd.results.log`
- Loki ingests osquery events from Alloy
- Falcosidekick successfully posts to Loki
- Falco loads the repo override from `config.d`
- Falco loads the local rules file with the ptrace and desktop auth helper exceptions
- the pinned images resolve correctly in Compose

## Remaining caveats

- Falco still reports LinuxKit / eBPF tracepoint attachment warnings on this host, so syscall coverage is only partially validated
- more aggressive synthetic Falco tests on this host did not produce reliable end-to-end detections, so desktop syscall evaluation should still be treated as environment-limited here
- the Grafana live-tail UI issue is still considered a Grafana-side behavior issue rather than a disk-optimization issue
- the installed `osqueryd` here does not expose `udev_read_buffer_size`, so that suggestion was reviewed but not applied


## STACK_EVAL_NOTES.md

# Stack Evaluation Notes

## What changed

### Loki / Grafana / Alloy / Falco stack
- Removed unnecessary host port publishing from the internal Loki read, write, and backend services.
- Removed the published `2801` host port from `falcosidekick`; Falco still reaches it over the Docker network.
- Added a consistent `/ready` route on the Loki gateway and hardened websocket proxy settings for tail requests.
- Bound MinIO to fixed host ports:
  - API: `9000`
  - Console: `9001`
- Switched the Alloy osquery bind mount to the repo-local path `./.data/osquery`.
- Updated the osquery setup flow to write results into `./.data/osquery`, which is visible to Docker Desktop based environments.
- Removed invalid osquery options from the JSON configs, added a repo-managed `osquery.flags`, and increased scheduler splay to reduce bursty execution.
- Tuned the default osquery profile to reduce high-volume low-value events by bounding process snapshots, narrowing `process_envs`, narrowing `process_memory_map`, reducing package and Docker inventory churn, and disabling pack-based duplication by default.
- Corrected the Falco config mounting so the container actually loads the intended overrides.
- Tuned Falco with `priority: warning`, `buffered_outputs: true`, a narrow local ptrace allowlist for crashpad noise, and a targeted desktop auth-helper exception for `/etc/shadow` and `/etc/pam.d/*` reads.
- Pinned Loki, Grafana, Alloy, Falco, Falcosidekick, OpenObserve, and the OTel Collector to exact image digests for more reproducible evaluation runs.

### OpenObserve comparison stack
- Added an optional `openobserve` profile to `docker-compose.yaml`.
- Added `otel-collector-config.yaml` so you can compare:
  - Loki + Grafana + Alloy
  - OpenTelemetry Collector Contrib + OpenObserve
- The collector currently supports:
  - file tailing for osquery via `./.data/osquery/osqueryd.results.log`
  - file tailing for Falco via `./.data/falco/events.jsonl`
  - generic OTLP log ingestion on `4317` and `4318`

## Current commands

### Start the Loki stack
```bash
docker compose up -d
```

### Start the OpenObserve comparison services
```bash
docker compose --profile openobserve up -d openobserve otel-collector
```

### Reconfigure host osquery to write to the repo-local directory
```bash
sudo ./setup-osqueryd.sh configure
sudo systemctl restart osqueryd
```

### Confirmed working
- Loki accepts pushes on `http://localhost:3100/loki/api/v1/push`.
- Loki `query_range` requests return results successfully.
- Alloy now tails and ships logs from `./.data/osquery/osqueryd.results.log` into Loki.
- Synthetic Falco payloads sent through Falcosidekick reach Loki successfully.
- The websocket tail endpoint upgrades successfully through the nginx gateway.
- Grafana reaches Loki through the Docker service name `gateway` instead of `localhost`.
- OpenObserve responds on `http://localhost:5080/healthz`.
- The OTel collector starts cleanly and watches `./.data/osquery/osqueryd.results.log`.
- The OpenObserve profile is isolated behind a Compose profile so it does not interfere with the Loki stack.

### Known blockers or partial blockers

#### 1. Host osquery logs were not visible inside Alloy when mounted from `/var/log/osquery`
This appears to be a Docker Desktop style host-path sharing issue in the current environment.

**Mitigation applied:**
- osquery output is redirected to `./.data/osquery`
- Alloy and the OTel collector both read from that repo-local path
- invalid osquery options were removed from the JSON configs
- CLI-only plugin settings are now installed via `osquery.flags`
- scheduler splay was raised from `10` to `25`

**What still must happen on the host:**
- rerun `setup-osqueryd.sh` so the installed host osquery config and flagfile are refreshed

**Suggestion reviewed but not implemented:**
- `udev_read_buffer_size` was not added because the installed `osqueryd` does not expose that flag in this environment

#### 2. Grafana live tail may still show an `undefined` UI error
Investigation showed:
- Loki push works
- Loki range queries work
- websocket upgrade on `/loki/api/v1/tail` works through the gateway
- Loki rejects instant log queries on `/loki/api/v1/query` with `400` because that API no longer supports log selectors as instant queries

That leaves the remaining symptom looking more like a Grafana Explore / datasource UI behavior issue than a Loki transport issue.

**Workaround:**
- use normal Explore range queries with auto-refresh while benchmarking

**Next likely mitigation if you want to keep chasing it:**
- pin Grafana to a specific non-`latest` version and test live tail again
- hard refresh the browser or test in a clean browser profile

#### 3. Falcosidekick host port conflict
The previous Compose file published `2801:2801`, which collided with an existing listener in this environment.

**Mitigation applied:**
- `falcosidekick` is now internal-only on the Docker network
- the Loki output was reconfigured with the supported `LOKI_HOSTPORT` style settings
- synthetic Falco payloads now POST through Falcosidekick to Loki successfully (`204` from the gateway)

#### 4. Falco runtime capture is only partially verified on this Docker Desktop / LinuxKit host
Falco now starts, loads the repo override from `config.d`, and loads the custom local rules file. It still logs several `libbpf` tracepoint attachment warnings on the LinuxKit kernel. That means the sidekick shipping path is configured and the noise-reduction overrides are active, while actual syscall coverage on this host still needs validation with real Falco detections.

**Additional validation attempted:**
- active `chrome_crashpad_handler` processes were present on the host during review
- no new crashpad ptrace alerts appeared in sampled Falco logs after the allowlist was loaded
- a synthetic ptrace reproduction using a `chrome_crashpad`-named symlink to `strace` was attempted, but the host denied the attach with `Operation not permitted` before a Falco alert could be compared against an unsuppressed baseline
- a more aggressive synthetic container test using execution from `/dev/shm` failed with `Permission denied` because that path is non-executable in this environment
- a harmless warning-level host test for the `Find AWS Credentials` rule also did not produce an observable Falco alert in this environment

So the override looks directionally correct, but this host still does not provide a fully conclusive end-to-end validation for real crashpad ptrace events, and it should not be treated as a reliable desktop syscall-eval environment for Falco.

#### 5. Falco is now mirrored into OpenObserve through a file-tail path
Falco -> Falcosidekick -> Loki remains the primary alerting path in this repo.

For the OpenObserve profile, Falco now also writes JSON events to `./.data/falco/events.jsonl`, and the OTel collector tails that file into the `falco` stream in OpenObserve. That keeps the Loki path intact while giving the comparison stack access to the same Falco event feed.

## Comparison notes

### Loki stack strengths in this repo
- already wired to Grafana
- Falco path already exists
- simple manual push/query validation

### OpenObserve comparison profile strengths in this repo
- single UI and storage layer for logs
- native OTLP ingestion path for future app instrumentation
- easy side-by-side comparison without replacing the Loki stack yet
