# Contributing

Thank you for considering a contribution.

This repository is currently oriented toward a lightweight local Linux monitoring workflow, so contributions are most useful when they preserve clarity, low write amplification, and local operability.

## Before contributing

Please read:

- `README.md`
- `EXPLAINER.md`
- `DISK_OPTIMIZATION.md`
- `PROJECT_PLAN.md`

These documents describe the repository's intended scope and design constraints.

## Contribution priorities

The most valuable contributions are usually:

- documentation improvements
- safer or clearer local setup behavior
- lower-noise Falco and osquery tuning
- benchmark automation and reproducibility improvements
- carefully scoped new log source integrations
- bug fixes that reduce environment-specific surprises

## What to avoid by default

Please be cautious about changes that:

- materially increase host-side disk writes
- add multiple always-on agents without an opt-in path
- widen the default stack footprint substantially
- assume a production deployment goal that the repo does not currently claim
- add environment-specific hacks without documenting why they are needed

## Suggested workflow

1. read the relevant documentation
2. make the smallest change that solves the problem
3. prefer explicit notes over hidden behavior
4. update documentation when behavior changes
5. validate the affected scripts or config where possible

## Documentation expectations

If your change affects setup, monitoring scope, or tradeoffs, update the relevant docs.

Common files to review when making changes:

- `README.md`
- `DOCUMENTATION_INDEX.md`
- `DISK_OPTIMIZATION.md`
- `STACK_EVAL_NOTES.md`
- `BENCHMARK_CHECKLIST.md`
- `BENCHMARK_CRITERIA.md`
- `LOG_SOURCE_EXPANSION.md`

## Configuration changes

When changing Falco, osquery, or Compose configuration:

- explain the operational tradeoff
- note whether the change affects disk writes
- note whether the change affects local resource footprint
- note whether the change is default behavior or opt-in behavior

## Testing guidance

At minimum, validate the part you changed.

For Falco and osquery config changes, the fastest local structural validation path is now:

- `uv sync`
- `uv run pytest`

If you already have the Docker stack running, you can also run the live integration checks:

- `uv run pytest --run-stack -m integration`

Use that alongside native validators when you change runtime behavior.

Examples:

- shell scripts: `bash -n`
- JSON configs: `python3 -m json.tool`
- Compose changes: `docker compose config`
- osquery config changes: `osqueryd --config_check`
- Falco rule changes: restart Falco and inspect startup logs
- repository config regression checks: `uv run pytest`

## Scope note

This repository still reflects a local evaluation environment more than a hardened public product. Good contributions help move it toward open-source clarity without losing the lightweight operating model that makes it useful.
