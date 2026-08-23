# Agent Instructions — LocalObserve

Guidance for AI agents and human reviewers operating in this repository.

## Scope & principles
- This is a local security observability pipeline (Falco, osquery, ClamAV,
  OpenObserve, rsigma, OTel Collector). Keep the container detection pipeline
  focused on **runtime** telemetry; source/CI controls (e.g., secret scanning)
  stay out of the runtime stack.
- The stack must remain bootable on **Docker, Podman, and Nerdctl**. Any change
  to `docker-compose.yaml`, runtime configs, or detection rules must not regress
  any of the three runtimes.
- Make minimal, surgical changes consistent with existing patterns.

## Reviewing changes: REVIEW AND TEST ASSUMPTIONS
Do not accept changes at face value. Explicitly surface and test the assumptions
behind them before approving or merging.

1. **Enumerate assumptions.** For every change, list the assumptions:
   network endpoints, external schemas/formats, daemon/engine availability,
   log field names, tool versions, and environment conditions.
2. **Verify against ground truth.**
   - Static/config checks: `uv run python -m pytest tests/`
   - Cross-runtime boot + detection checks: `bash ./scripts/verify-runtimes.sh`
     (or `task verify-runtimes`)
   - Validate configs against real binaries when present:
     `otelcol --config <file> validate`, `betterleaks config check`,
     `falco --list rules`.
3. **Flag unverifiable assumptions as explicit risks.** If a check cannot run in
   the sandbox (e.g., no container daemon, unreachable external feed), say so in
   the review rather than letting it pass silently. Calls out "tested locally on
   all 3 runtimes" only when it was genuinely executed.
4. **Keep tests hermetic.** Mock external network calls; never require live
   egress to pass a unit test. Prefer `--dry-run`/offline-safe paths.

## Repo-specific assumptions to challenge
- **External feed URLs** (e.g., `mthcht/awesome-lists` paths in
  `tools/sync_threat_intel.py`) are best-effort guesses until actually fetched;
  verify the real paths before relying on live data.
- **Log field names** used in filters/rules (e.g., `body["log_type"]` in the
  OTTL processor) must match the live event schema; confirm, don't assume.
- **`mise` installs CLIs only.** `docker-cli`/`nerdctl`/`podman`/`docker-compose`/
  `betterleaks` in `mise.toml` are client binaries; the dockerd / containerd /
  podman-server **engines** come from the host, not from `mise`.
- **`podman` via mise on Linux is the remote client (`podman-remote`).** Kernel
  syscall monitoring still requires a podman machine/server (often rootful).
- **Container engines are not guaranteed in CI.** Acceptance for "boots on all
  three runtimes" depends on the host providing the engines; treat missing
  engines as a skipped/blocked check, not a failure.
