# Network observability evaluation: GoFlow2, Snitch, and OpenSnitch

Status: **ready for controlled benchmarking** (2026-11-12 UTC). GoFlow2 and
Snitch have Docker smoke-test results below. OpenSnitch is intentionally not
installed on the LocalObserve host and requires the disposable-VM procedure in
section 5.

## 1. Compare capabilities, not just resource usage

Snitch is **not a drop-in replacement** for GoFlow2, and OpenSnitch is not a
replacement for either collector. They answer different questions:

| Capability | GoFlow2 v1.3.8 | Snitch v0.2.2 | OpenSnitch v1.8.0 |
|---|---|---|---|
| Primary input | NetFlow v5/v9, IPFIX, sFlow exporters | Live Linux `/proc/net/*` and `/proc/<pid>/fd` | Host connections intercepted by its daemon/eBPF/netfilter path |
| Historical flow records | Yes, via JSONL -> OTel -> OpenObserve | Only if snapshots/frames are shipped | Connection/verdict events; SIEM integration available |
| Byte/packet counters from exporters | Yes | No equivalent to NetFlow/sFlow accounting | Not a NetFlow/sFlow decoder |
| Host PID/process attribution | No | Yes, when host PID namespace and `/proc` permissions allow | Yes; this is a core use case |
| Remote/router visibility | Yes | No | No |
| Active outbound firewall | No | No | Yes |
| LocalObserve deployment | `netflow` container profile | `network-inspect` distroless container profile | Separate host/VM package only |

The evaluation should therefore select a **combination** based on the required
telemetry: GoFlow2 for exporter/router history, Snitch for low-complexity local
socket inspection, and OpenSnitch when process-aware outbound policy is a
requirement.

## 2. Log-driven fixes already applied

### GoFlow2

- The initial bind-mounted `flows.jsonl` had incompatible ownership and caused a
  restart loop. Precreate its directory before starting (`install -d` below);
  do not run GoFlow2 as root to work around ownership errors.
- A synthetic NetFlow v5 datagram to UDP 2055 produced
  `NetFlow/IPFIX version error: 5`. Ground-truth upstream documentation and the
  running binary confirm that `netflow://` handles v9/IPFIX while `nfl://` is
  required for v5. The compose service now exposes:
  - UDP 2055: NetFlow v9/IPFIX (`netflow://`)
  - UDP 2056: NetFlow v5 (`nfl://`)
  - UDP 6343: sFlow (`sflow://`)
- The unfiltered sample contained 70 JSON fields and occupied 1,227 bytes,
  including empty custom fields and per-label MPLS expansions. The new selector
  retains common timing, routing, L2-L4, ASN, BGP, and MPLS-summary fields. The
  identical sample then contained 48 fields and occupied 835 bytes: **32.0%
  less JSONL input**. Vendor-specific `Custom*` fields and individual MPLS label
  stacks are excluded; remove `-format.selector` when those are required.
- A live OpenObserve query also showed the original JSON in `body` alongside
  the flattened attributes: `file_log`'s JSON parser populates attributes but
  retains the raw body. `transform/goflow2` now clears that body after deleting
  raw payload attributes, avoiding duplicate indexed content and preventing a
  raw-body redaction bypass. OpenObserve lowercases the resulting attribute
  names (`SrcAddr` -> `srcaddr`).
- Workers remain at the upstream default of 1. Do not increase workers or reduce
  the 256 MiB memory ceiling until loaded results demonstrate a need.

### Snitch

- `images/snitch/Dockerfile` builds Snitch v0.2.2 with `CGO_ENABLED=0` and Go
  1.27.3, then copies only the static binary into
  `gcr.io/distroless/static-debian12:nonroot`. The resulting amd64 image is
  11.38 MiB and has no shell or package manager.
- Upstream's current README advertises `snitch ls -n`, but the pinned v0.2.2 CLI
  rejects that shorthand. Use `snitch ls --resolve-addrs=false -o json`.
- On this host, nonroot + `SYS_PTRACE` yielded zero process socket mappings.
  Root + `SYS_PTRACE` still saw only 27 inodes under the default AppArmor
  profile. Root + `SYS_PTRACE` + `apparmor=unconfined` resolved approximately
  1,620 inodes and real host PIDs/process names. The opt-in compose profile uses
  the last configuration, with a read-only rootfs and **without** full
  `privileged` mode. For a safer socket-only fallback, set `user: "65532:65532"`
  and remove `apparmor=unconfined`; expect empty PID/process fields.
- Snitch emits full socket frames every five seconds. These frames contain host
  addresses, process command lines, and working directories; Docker json-file
  rotation is capped at 3 x 10 MiB and output is not yet wired into
  OTel/OpenObserve. Benchmark frame volume before lowering the interval. The
  distroless image does not contain the host user database, so `user` is a
  numeric UID even when PID/process attribution succeeds.

A 60-second mixed smoke run (`idle-20261111-212000`) sent 600 v5 datagrams at
10 datagrams/second while both candidates were running. All 600 decoded without
new GoFlow2 errors. The harness passed its budgets and observed maxima of
8.3 MiB / 0.4% CPU for GoFlow2 and 19.0 MiB / 10.2% CPU for Snitch. This was not
an isolated or statistically valid comparison; use the separate phases below.

`tools/bench_stack.py` now also samples candidate Docker json-file output bytes
for GoFlow2 and Snitch and reports `Docker Logs (MiB/min)`. This is distinct
from cgroup write rate: the logical Docker-log rate captures the candidate's
serialized event volume even when host page-cache accounting or raw Docker
log-path permissions make the cgroup delta unavailable.

## 3. Reproduce the smoke checks

```bash
# Precreate the UID-1000-writable bind mount before the first GoFlow2 start.
install -d -m 0775 .data/goflow2

docker compose --profile netflow up -d goflow2
docker compose --profile network-inspect up -d --build snitch

# Send only RFC 5737 documentation-address metadata to loopback.
python3 tools/netflow_probe.py --count 1

# Confirm the record decoded and the OTel receiver is watching the file.
python3 -c 'import json, pathlib; p=pathlib.Path(".data/goflow2/flows.jsonl"); print(json.loads(p.read_text().splitlines()[-1]))'
docker logs --since 5m localobserve-goflow2-1
docker logs --since 5m localobserve-otel-collector-1

# Confirm distroless execution and host process attribution.
docker compose --profile network-inspect exec snitch version
docker compose --profile network-inspect exec snitch ls --resolve-addrs=false -o json
```

Expected GoFlow2 probe values include `Type=NETFLOW_V5`,
`SrcAddr=192.0.2.10`, `DstAddr=198.51.100.20`, `DstPort=443`, `Packets=120`, and
`Bytes=60000`. OTel uses `start_at: end`, so existing/probe history is not proof
of OpenObserve ingestion; send a new probe after the `Started watching file`
message and query the `netflow` stream separately.

## 4. Controlled GoFlow2/Snitch resource benchmark

Use the same host, core-stack state, duration, and sample interval for every
run. Keep other profile-gated services stopped. A 15-minute window is the
minimum recommended duration; the commands below use five minutes for a quick
iteration.

Run the complete phase sequence automatically. It stops both candidates for a
core baseline, runs GoFlow2 with `duration x rate` synthetic records, then runs
Snitch with a held local TCP connection; repeats each phase and writes copied
run directories plus compare logs under `.artifacts/bench/network-eval/`:

```bash
DURATION=900 INTERVAL=10 REPEATS=3 RATE=10 task bench-network
task bench-network-report
```

The report averages the *maximum* RAM/CPU and MiB/min rates from each completed
phase, so it is a median-of-window-results rather than a percentile distribution
across every 10-second sample.

Use these phases manually when isolating one candidate:

1. **Core baseline**: stop both candidates, then run the harness.
2. **GoFlow2 only**: start GoFlow2, generate a fixed local packet rate, and run
   the same harness. Record offered datagrams, decoded JSONL records, decoder
   errors, JSONL growth, CPU, RAM, and cgroup writes.
3. **Snitch only**: stop GoFlow2, start Snitch with the same five-second frame
   interval, hold a controlled local TCP connection open, and run the harness.
   Record frame count/size, socket count, attribution coverage, CPU, RAM, and
   writes.
4. Repeat each phase at least three times and report medians plus range. Do not
   average away decoder errors or missing process attribution.

```bash
# Baseline
docker compose stop goflow2 snitch
uv run python tools/bench_stack.py --scenario idle --duration 300 --interval 10

# GoFlow2 loaded run (start the probe in a second terminal)
docker compose --profile netflow up -d goflow2
python3 tools/netflow_probe.py --count 3000 --rate 10
uv run python tools/bench_stack.py --scenario idle --duration 300 --interval 10

# Snitch run with a harmless held connection to the existing local OpenObserve port
docker compose stop goflow2
docker compose --profile network-inspect up -d snitch
python3 -c 'import socket,time; s=socket.socket(); s.connect(("127.0.0.1",5080)); time.sleep(300)'
uv run python tools/bench_stack.py --scenario idle --duration 300 --interval 10

# Compare explicit run IDs; lexicographic "latest" may mix phases.
uv run python tools/bench_compare.py <baseline-run-id> <goflow2-run-id>
uv run python tools/bench_compare.py <baseline-run-id> <snitch-run-id>
```

The held-connection command blocks for the sample window; run it in a separate
terminal or background it. The NetFlow probe is a collector load generator, not
a packet-level counterpart of that TCP connection. Do not claim event-for-event
correlation between these workloads.

Acceptance gates:

| Dimension | GoFlow2 gate | Snitch gate |
|---|---|---|
| Correctness | Offered valid records decode without unexpected errors; required fields survive selection | All visible sockets have valid addresses/state; measure PID/process coverage separately |
| Resource | Record max/median CPU and RAM, JSONL and cgroup writes per accepted flow | Record max/median CPU and RAM, Docker log writes per socket/frame |
| Latency | UDP send -> JSONL -> OpenObserve searchable | Socket creation -> next emitted frame; bounded by poll interval |
| Safety | No root workaround; JSONL rotation remains active | No full `privileged`; read-only rootfs and capped logs remain active |
| Fitness | Required for NetFlow/IPFIX/sFlow history | Useful for ad-hoc/local host sockets; not an exporter replacement |

## 5. OpenSnitch: disposable-host evaluation only

OpenSnitch v1.8.0 is a host application firewall, not a container-only passive
probe. Its daemon may load eBPF programs and change nftables rules. Installing
it on the active LocalObserve host could disrupt exactly the network telemetry
being measured, so it is deliberately absent from `docker-compose.yaml` and was
**not run** in this preparation.

Use a snapshot-backed, **disposable Linux VM** with a supported kernel and no
production workloads:

1. Download the v1.8.0 daemon and GUI packages from the official OpenSnitch
   release and verify the publisher signature before installation. Follow the
   upstream installation documentation for the VM's distribution. The v1.8.0
   GUI uses PyQt6; check distribution compatibility first.
2. Snapshot the VM and record its existing nftables/eBPF state. Start in an
   observe/allow configuration and verify that no unexpected deny rule is
   active before generating traffic. Do not test enforcement on a remote SSH
   session without an out-of-band console.
3. Measure the daemon and GUI separately (`systemd-cgtop`, `pidstat`, and VM
   disk/io.stat), because `tools/bench_stack.py` only sees Docker compose
   services. Use the same 15-minute windows and local client/server workload
   for baseline, observe/allow, interactive-prompt, and explicit-deny phases.
4. Record process-attribution coverage, prompt/verdict latency, false positives,
   dropped/allowed connection counts, daemon RAM/CPU, SIEM event rate, and disk
   writes. Validate both IPv4 and IPv6 where supported.
5. Test fail-closed behavior deliberately: stop the daemon, exercise a denied
   test destination, and document whether the VM matches the desired policy.
   Restore the snapshot afterward and verify no rules remain.

The OpenSnitch acceptance gate is primarily **safe, correct process-aware
policy**. Resource numbers from its host daemon must not be presented as a
like-for-like container image comparison with GoFlow2 or Snitch.

## 6. Validation boundaries and assumptions

- Docker smoke tests were executed locally. Podman and Nerdctl engines were not
  validated for these profiles; `apparmor=unconfined`, host PID namespaces, and
  build support must be checked on each runtime before claiming compatibility.
- GoFlow2's live JSON field names were verified with NetFlow v5. NetFlow v9,
  IPFIX, and sFlow still require exporter-specific tests, including template
  handling and the selector's effect on vendor fields.
- Snitch v0.2.2 reads `/proc`; it cannot see remote flows and can miss short-lived
  sockets between polls. Host LSM policy materially changes attribution.
- OpenSnitch results are pending an isolated VM. No enforcement, kernel
  compatibility, SIEM schema, or resource claim is made here.
