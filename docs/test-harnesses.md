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
