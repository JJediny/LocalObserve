# System Testing Plan

## 1. Current Test Coverage Summary
*   **Static Configuration Testing (`pytest`)**: Python tests validate `osqueryd.conf`, `falco-config.yaml`, and `falco_rules.local.yaml` to ensure schema compliance and proper key-value structures.
*   **Daemon Syntax Testing (`pytest`)**: Custom tests validate `alloy-local-config.yaml` using `grafana/alloy fmt` and `loki-config.yaml` using `grafana/loki -verify-config`.
*   **Live Harness Testing (`go-task`)**: Go binaries (`osqtool` and `event-generator`) run dynamic checks against the live osquery schema and actual kernel system calls.
*   **E2E Stack Integration (`pytest --run-stack`)**: Synthesizes Falco events and confirms they successfully traverse the `falcosidekick -> loki-write -> loki-read -> openobserve` pipeline.

## 2. Identified Gaps & Missing Coverage
While structural validation and pipeline traversal are verified, the following areas lack automated testing:

1.  **Log Volume Baselines**: Tests should assert that `osqueryd` and `journald` do not emit more than *X* megabytes of telemetry per hour, preventing silent log spam regressions.
2.  **Resource Constraints (OOM/CPU)**: Docker container bounds (e.g., Loki write limits, Alloy memory limits) are currently not asserted in the test suite. We need tests that parse `docker-compose.yaml` to ensure `mem_limit` and `cpus` are strictly enforced.
3.  **Alloy Parsing Accuracy**: Regex/JSON parsing stages in `alloy-local-config.yaml` (especially `stage.regex` for syslog/dpkg) are not unit-tested against mock log lines.

## 3. Proposed Testing Implementation Plan
1.  **Add `test_alloy_pipelines.py`**: Mount a mock `test.log` into a standalone Alloy container and assert the output matches expected JSON payloads to guarantee parsing accuracy.
2.  **Add `test_resource_limits.py`**: Parse `docker-compose.yaml` using `pyyaml` to assert that every container specifies CPU and memory constraints.
3.  **Integrate Metrics Assertions**: Extend the `test_stack_integration.py` suite to query Loki's internal metrics endpoint (`/metrics`) and assert that the ingestion rate is functioning optimally and not hitting `429 Too Many Requests`.
