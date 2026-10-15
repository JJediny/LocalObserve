# ADR 0001: Dynamic Mermaid coverage map for the README

- Status: Proposed
- Date: 2026-10-15

## Context

The README lists tools but gives no at-a-glance view of which parts of the Linux
stack LocalObserve actually instruments. Brendan Gregg's
[Linux Performance observability tools diagram](https://www.brendangregg.com/linuxperf.html)
(layered: applications, system libraries, system-call interface, kernel
subsystems, devices) is the stable spatial model we want to follow. The idea of
expressing it with Mermaid `block-beta` and class-based status colors comes from
the research notes supplied with this task; the layered-map concept is Gregg's.

## Decision

1. Use Mermaid **`block-beta`** (block diagram) for a README-embedded,
   layered coverage map. Mermaid supports explicit columns, nested blocks,
   column spanning and reusable `classDef` styling
   ([Block Diagram Syntax](https://mermaid.js.org/syntax/block.html)).
   GitHub renders Mermaid natively; the renderer must support `block-beta`.
2. Separate three concerns:

   | Concern | Representation |
   |---|---|
   | Architecture | Stable block IDs, layers, nesting, spans (`docs/templates/coverage-architecture.yaml`) |
   | Instrumentation | Component(s) per subsystem, each linking to a file in this repo |
   | Status | Generated `class` assignments plus a status word in each label (`docs/templates/coverage-status.json`) |
3. Generation pipeline: `architecture YAML + status JSON -> Mermaid text -> README block`
   between `<!-- coverage-map:start -->` / `<!-- coverage-map:end -->` markers.
4. Status means **coverage** (not operational health):

   | Status | Class | Meaning |
   |---|---|---|
   | OK | `healthy` | telemetry enabled and fresh |
   | PARTIAL | `degraded` | partial coverage or delayed data |
   | GAP | `missing` | required telemetry missing |
   | UNKNOWN | `stale` | not evaluated / stale |

   Color is never the only signal: the status word stays in the label.
5. "Implemented" is evidenced by repo state: a component is `OK` only if its
   config/rule files linked from the architecture file exist; otherwise `GAP`.
   Runtime freshness (data actually arriving) is out of scope for the static
   generator and must be set explicitly in the status JSON.

## Alternative view: logging paths

If a logging-path view is wanted (kernel messages, `/dev/log`, `systemd-journald`,
`rsyslog` -> OTel Collector), model it as a second architecture YAML using the
same generator; it is a different map from Gregg's observability diagram and is
not covered by this ADR's first iteration.

## Consequences

- Topology is independent of the monitoring backend; status is a replaceable data layer.
- Mermaid block diagrams do not support clickable links per block reliably, so
  component links live in a table under the diagram (generated from the same YAML).
- Tests for any generator must be hermetic (no network) and verify that each
  linked path exists. Generator implementation is a follow-up; see
  `docs/templates/coverage-map-template.md`.
- Alternative considered: flowchart with subgraphs (supports `click` links and
  edges, but weaker layered layout).

## References

- Brendan Gregg, Linux Performance (original observability, benchmarking and tuning diagrams; stacked boxes with applications on top, kernel subsystems in the middle, hardware at the bottom, tools beside the components they inspect): https://www.brendangregg.com/linuxperf.html
- Brendan Gregg, Linux Performance Tools 2014 (background): https://www.brendangregg.com/blog/2014-11-22/linux-perf-tools-2014.html
- Mermaid block diagram syntax: https://mermaid.js.org/syntax/block.html
- Mermaid flowchart syntax: https://mermaid.js.org/syntax/flowchart.html
