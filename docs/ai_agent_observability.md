# AI Agent Session Observability (issue #91)

LocalObserve captures AI agent sessions — tool calls, permissions context, errors, and security-relevant behavior — and evaluates them with Sigma detections in real time. Any agent that speaks OTLP works out of the gate; Python agents (including Logfire users) get a one-line integration.

## Architecture

```
agent (opencode / pi harness / any OTLP app / logfire)
        │  OTLP/HTTP :4318 (or gRPC :4317)
        ▼
  otel-collector ──► filter: service.namespace == "ai-agents"
        │                         │
        │ (agent logs)            │ (everything else)
        ▼                         ▼
  transform/agent_redact     logs/otlp → OpenObserve `otlp_logs`
        │  (strips prompts/completions
        │   unless ai.capture_prompts=true)
        ├──► OpenObserve stream `agent_logs`
        └──► rsigma daemon → Sigma rules → webhook → alert-receiver
                                        └► desktop notification
```

- **Session identity**: one session = one `ai.session.id` (and, for traced agents, one W3C `trace_id`). Tool calls are OTLP log records tagged with the session id.
- **Routing key**: resource attribute `service.namespace=ai-agents`. Anything without it flows through the generic OTLP pipeline unchanged.
- **Detections**: `rules/sigma/active_rules/ai_agent_*.yaml` (see below). The rsigma pipeline maps the flattened attributes onto the Sigma idiom fields (`gen_ai_tool_args` → `CommandLine`, `gen_ai_tool_name` → `Image`).

## Quick start

1. The stack is already wired — nothing to enable. Start it if needed:
   ```bash
   docker compose up -d
   ```
2. Emit a synthetic session (also used by the e2e test and the `agent` benchmark scenario):
   ```bash
   uv run python tools/agent_session_demo.py
   ```
3. Verify:
   ```bash
   uv run python -m pytest tests/test_agent_session_e2e.py --run-stack -v
   ```
   Then open OpenObserve (http://localhost:5080) → dashboards → **AI Agent Sessions**,
   or query directly:
   ```sql
   SELECT * FROM "agent_logs" ORDER BY _timestamp DESC LIMIT 50
   ```

## Python agents (works out of the gate)

Add this as the first import in your agent entrypoint:

```python
import agent_otel_prelude  # noqa: F401  — configures the session shipper

agent_otel_prelude.emit_tool_call("read_file", "/workspace/src/main.py")
agent_otel_prelude.emit_tool_call(
    "run_shell", "cargo build --release",
    ok=False, error="exit code 101",
)
```

The prelude (`tools/agent_otel_prelude.py`):
- reads `AGENT_OTLP_HTTP_ENDPOINT` (default `http://localhost:4318`, falling back to the repo `.env`'s `OTEL_EXPORTER_OTLP_ENDPOINT`; a `:4317` gRPC endpoint is auto-rewritten to `:4318` HTTP)
- generates `ai.session.id` (exposed as `agent_otel_prelude.SESSION_ID`)
- tags the session resource with `service.namespace=ai-agents` so the collector routes it
- configures **Logfire** with `send_to_logfire=False` when logfire is installed — so any logfire-instrumented library (OpenAI, Anthropic, pydantic-ai, MCP servers) exports into this same pipeline with zero extra setup:
  ```bash
  uv add logfire
  ```
- privacy: sets `ai.capture_prompts=false` unless `AGENT_CAPTURE_PROMPTS=true`

### Logfire-only agents
If your agent already uses Logfire, you don't need the prelude's emit helpers — just configure logfire the same way:

```python
import os
os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
os.environ.setdefault("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")

import logfire
logfire.configure(service_name="my-agent", send_to_logfire=False)
```

and tag the session resource with `service.namespace=ai-agents` (the prelude does this for you; standalone logfire setups can pass `resource_attributes` or set `OTEL_RESOURCE_ATTRIBUTES=service.namespace=ai-agents`).

## Non-Python agents (opencode, pi harness, anything OTLP)

Point the agent's OTLP exporter at the collector:

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318     # HTTP/protobuf
# or http://localhost:4317 for gRPC
OTEL_RESOURCE_ATTRIBUTES=service.namespace=ai-agents
```

- **opencode**: enable its OpenTelemetry export and set the two env vars above in the shell/service that launches it. (The exact config key varies by opencode version — check `opencode --help` for the OTEL flag; any OTLP-capable version works with the env vars alone.)
- **Session files** (optional fallback for agents that can't export OTLP): write newline-delimited JSON events to `./.data/agent-sessions/*.jsonl` — the directory is mounted read-only into the collector container at `/var/log/agent-sessions` for a `file_log` receiver to tail (wire-up is a two-line collector change when needed).

## Attribute conventions

| Attribute | Where | Purpose |
|---|---|---|
| `service.name` | resource | agent app name (shows in dashboard `$service` variable) |
| `service.namespace` | resource | **must be `ai-agents`** for routing |
| `ai.session.id` | resource | session correlation key |
| `ai.agent.name` | resource | display name |
| `ai.capture_prompts` | resource | `true` opts the session into prompt capture (default: redacted) |
| `gen_ai.tool.name` / `gen_ai_tool_name` | log | tool name (Sigma `Image`) |
| `gen_ai.tool.args` / `gen_ai_tool_args` | log | tool arguments (Sigma `CommandLine`) |
| `otel.status_code` | log | `OK` / `ERROR` for error-rate alerting |

## Sigma detections (rsigma)

| Rule | Level | MITRE |
|---|---|---|
| AI Agent Dangerous Shell Command | high | T1059, T1561.002 |
| AI Agent Sensitive File Access | high | T1003, T1565.001 |
| AI Agent Credential File Read | critical | T1552.001/.004 |
| AI Agent Workspace Escape Attempt | medium | T1083 |
| AI Agent Suspicious Network Egress | medium | T1071 |

Add rules by dropping a YAML file into `rules/sigma/active_rules/` (logsource `product: ai_agent`, `service: otel`) — rsigma hot-reloads. Alerts flow through the existing `webhooks/alert_receiver.yaml` → alert-receiver → desktop notification path.

## OpenObserve alerts

Two GitOps-managed alerts (see `alerts/openobserve/alerts.json`, provisioned by `task sync-oo-import`):
- **AIAgent-Sensitive-File-Access** — any tool call touching shadow/sudoers/sshd_config/authorized_keys/ld.so.preload
- **AIAgent-Tool-Error-Spike** — ≥5 tool errors in 5 minutes (prompt-injection probing indicator)

## Privacy model

- **Default**: `transform/agent_redact` deletes `gen_ai.prompt`, `gen_ai.completion`, `gen_ai.system`, `llm.prompts`, `llm.completions`, `mcp.tool_arguments`, `mcp.tool_result` at the collector. Prompts never reach disk.
- **Opt-in capture**: set `AGENT_CAPTURE_PROMPTS=true` (env) — the prelude stamps `ai.capture_prompts=true` on the session resource, and the collector skips redaction for that session only.
- Tool *arguments* (`gen_ai_tool_args`) are retained by design — they are the detection signal. Don't put secrets in tool arguments; if you must, extend the redaction list in `otel-collector-config.yaml`.

## Benchmarking agent overhead

The agent workload is part of the Part A benchmark harness:

```bash
uv run python tools/bench_stack.py --scenario agent --duration 120
```

This runs `tools/agent_session_demo.py` and measures the marginal RAM/SSD cost of session capture against the budgets in `tools/bench_budgets.json`.
