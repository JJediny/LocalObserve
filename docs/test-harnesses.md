# Security Test Harnesses

This project utilizes specialized Go-based testing harnesses to programmatically validate the security telemetry infrastructure without relying solely on static linting.

## Harness 1: osqtool (Osquery Configuration Validation)

`osqtool` is used to validate the syntax, schema compliance, and query cost of our `osqueryd.conf` scheduled queries against the real osquery daemon schema.

### Features:
*   **Syntax & Schema Validation**: Executes scheduled queries locally via `osqueryi` to guarantee the syntax is correct and the queried columns/tables actually exist in the currently deployed osquery version.
*   **Performance Benchmarking**: Calculates the daily query execution cost and execution time by dry-running queries, ensuring high-frequency scheduled queries do not starve system resources.
*   **Lock Contention Prevention**: Runs safely in CI/CD by avoiding concurrent `osqueryi` locking bottlenecks using precise worker configurations.

### Usage:
The testing harness uses `go-task` to extract the `schedule` block from `osqueryd.conf` and test it via `osqtool`.

```bash
task test-osquery
```
*(Under the hood, this extracts queries into a pack and runs `osqtool verify --workers 1 tests/test_pack.conf`)*

---

## Harness 2: event-generator (Falco eBPF Validation)

`falcosecurity/event-generator` is used to directly trigger live kernel system calls in the execution environment to ensure the eBPF sensors and Falco rules successfully trap malicious behaviors.

### Features:
*   **Real-World System Calls**: Rather than parsing rule text, this tool executes the literal C-level system calls (e.g., `open("/etc/shadow")` or `execve` inside a namespace container).
*   **End-to-End Validation**: Guarantees that the entire pipeline—from the eBPF kernel probe, to the Falco daemon, to the `falcosidekick` router, down to the Loki storage—is fully functional and capturing telemetry.
*   **Coverage**: Iterates through the full suite of Linux CISA KEV (Known Exploited Vulnerabilities) indicators and rootkit behaviors.

### Usage:
The harness downloads the pre-compiled upstream binary to avoid local Go module conflicts, and runs it directly on the host to generate events.

```bash
task test-falco
```
*(Under the hood, this fetches the binary and runs commands like `./event-generator run syscall.ReadSensitiveFileUntrusted`)*

---

## Running the Complete Suite

To execute all integration harnesses sequentially:

```bash
task test
```

---

## Harness 3: CALDERA Ability Execution with OTEL Tracing

This repository also includes a Python harness that clones CALDERA plus the stockpile plugin data locally, executes selected Linux abilities directly on the host, and emits an OTEL trace to the local collector so execution can be reviewed in OpenObserve traces.

### Features:
*   **Host execution**: Runs a CALDERA stockpile ability command on the local host rather than inside a container.
*   **Curated Linux-safe allowlist**: Exposes a small vetted set of low-risk discovery abilities, including payload-backed cases.
*   **Payload staging**: Copies referenced stockpile payloads into a temporary execution directory before running payload-dependent abilities.
*   **Trace correlation**: Emits a span through `http://localhost:4318/v1/traces` and verifies the resulting `trace_id` is queryable in OpenObserve.
*   **Safe default**: Uses stockpile ability `52177cc1-b9ab-4411-ac21-2eadc4b5d3b8` (`ls`) for the built-in test path.

### Usage:

```bash
task bootstrap-caldera
task list-safe-caldera-abilities
task test-host-emulation
```

You can also run the harness directly:

```bash
uv run python tools/caldera_otel_harness.py run-ability --bootstrap --ability-id 52177cc1-b9ab-4411-ac21-2eadc4b5d3b8 --verify-trace
```

Payload-backed abilities are also supported. Example:

```bash
uv run python tools/caldera_otel_harness.py run-ability --bootstrap --ability-id a0676fe1-cd52-482e-8dde-349b73f9aa69 --verify-trace
```

If you want the harness to also query OpenObserve logs for payload-related events in the same time window, add `--verify-logs`.

ClamAV is now optional by default. Start it only when you want a filesystem scan:

```bash
docker compose --profile scan up -d clamav clamav-scanner
```

For pytest-based verification, use:

```bash
uv run python -m pytest tests/test_caldera_otel_integration.py --run-stack --run-host-emulation -v
```

> Note: the CALDERA Git repository is not itself a Python package, so it is bootstrapped into `.data/caldera` rather than installed as a `uv` dependency.
