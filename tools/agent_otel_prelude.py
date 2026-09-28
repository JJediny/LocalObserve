"""Agent OTEL prelude — one import gives any Python agent LocalObserve session capture.

Import this module as the very first thing in an agent entrypoint::

    import agent_otel_prelude  # noqa: F401  (configures the OTLP session shipper)

What it does (issue #91):
  * Ships agent tool-call events as OTLP log records to the LocalObserve
    collector (HTTP/protobuf on :4318 by default). The collector routes them to
    the `agent-logs` stream in OpenObserve and evaluates them with rsigma
    (rules/sigma/active_rules/ai_agent_*.yaml).
  * Tags the session with `service.namespace=ai-agents` (the routing key) and
    `ai.session.id` for dashboard correlation.
  * Configures Logfire when installed (``uv add logfire``) with
    send_to_logfire=False so any logfire-instrumented library (OpenAI,
    Anthropic, pydantic-ai) also flows into this collector.
  * Privacy: unless AGENT_CAPTURE_PROMPTS=true the session sets
    ai.capture_prompts=false, and the collector's transform/agent_redact
    processor strips prompt/completion payloads from stored logs.

Environment (checked first in the real env, then the repo's .env):
  AGENT_OTLP_HTTP_ENDPOINT   default http://localhost:4318
  AGENT_CAPTURE_PROMPTS      "true" to keep LLM prompt/completion payloads
  AGENT_SERVICE_NAME         default "agent-demo"
"""
from __future__ import annotations

import atexit
import logging
import os
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SESSION_ID = uuid.uuid4().hex

_DEFAULT_ENDPOINT = "http://localhost:4318"


def _load_repo_env() -> dict[str, str]:
    """Minimal .env loader (no external deps) for repo-standard vars."""
    env: dict[str, str] = {}
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return env
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


_REPO_ENV = _load_repo_env()


def env_var(name: str, default: str | None = None) -> str | None:
    """Precedence: real environment, then repo .env, then default."""
    return os.environ.get(name) or _REPO_ENV.get(name) or default


def otlp_http_endpoint() -> str:
    """Agent log shipping endpoint. Prefers OTLP HTTP (:4318).

    The repo .env defaults OTEL_EXPORTER_OTLP_ENDPOINT to gRPC :4317 for the
    caldera harness; the agent path uses HTTP/protobuf (the only OTLP exporter
    in the dev dependency group), so a :4317 endpoint is rewritten to :4318.
    """
    endpoint = str(
        env_var("AGENT_OTLP_HTTP_ENDPOINT")
        or env_var("OTEL_EXPORTER_OTLP_ENDPOINT")
        or _DEFAULT_ENDPOINT
    )
    if endpoint.endswith(":4317"):
        endpoint = endpoint[: -len("4317")] + "4318"
    return endpoint


CAPTURE_PROMPTS = str(env_var("AGENT_CAPTURE_PROMPTS", "false")).lower() == "true"
SERVICE_NAME = str(env_var("AGENT_SERVICE_NAME", "agent-demo"))


def session_resource() -> dict[str, object]:
    """Resource attributes identifying this agent session."""
    return {
        "service.name": SERVICE_NAME,
        "service.namespace": "ai-agents",
        "ai.session.id": SESSION_ID,
        "ai.agent.name": SERVICE_NAME,
        "ai.capture_prompts": CAPTURE_PROMPTS,
    }


_log = logging.getLogger("agent_otel_prelude")


def _configure_logfire() -> bool:
    """Optional: configure Logfire to export OTLP to this collector (no Logfire backend)."""
    try:
        import logfire  # type: ignore[import-not-found]
    except ImportError:
        return False

    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", otlp_http_endpoint())
    os.environ.setdefault("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
    logfire.configure(
        service_name=SERVICE_NAME,
        send_to_logfire=False,  # local-first: OpenObserve is the backend
        console=False,
    )
    _log.debug("logfire configured to export OTLP to %s", otlp_http_endpoint())
    return True


_PROVIDER = None


def _get_provider():
    """Lazily build (once) the OTLP HTTP LoggerProvider for tool-call events."""
    global _PROVIDER
    if _PROVIDER is not None:
        return _PROVIDER
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

    endpoint = otlp_http_endpoint()
    resource = Resource.create(session_resource())
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(endpoint=f"{endpoint}/v1/logs"),
            schedule_delay_millis=500,
        )
    )
    atexit.register(provider.shutdown)
    _PROVIDER = provider
    return provider


def emit_tool_call(
    tool_name: str,
    tool_args: str,
    *,
    ok: bool = True,
    error: str | None = None,
    extra_attributes: dict[str, object] | None = None,
) -> None:
    """Emit one agent tool-call event as an OTLP log record.

    The rsigma ai_agent rules match on the flattened attributes:
      gen_ai_tool_name  -> Sigma 'Image' (via the pipeline field mapping)
      gen_ai_tool_args  -> Sigma 'CommandLine'
      ai_session_id     -> session correlation key on the dashboard
    """
    import time as _time

    from opentelemetry._logs import LogRecord
    from opentelemetry._logs.severity import SeverityNumber

    attributes: dict[str, object] = {
        # Canonical GenAI semconv keys (kept by the collector as-is)
        "gen_ai.tool.name": tool_name,
        "gen_ai.tool.args": tool_args,
        # Flattened keys used by the rsigma pipeline mapping + OpenObserve SQL
        "gen_ai_tool_name": tool_name,
        "gen_ai_tool_args": tool_args,
        "ai_session_id": SESSION_ID,
        "ai.agent.name": SERVICE_NAME,
        "ai.capture_prompts": CAPTURE_PROMPTS,
        "otel.status_code": "OK" if ok else "ERROR",
    }
    if error:
        attributes["error.message"] = error
    if extra_attributes:
        attributes.update(extra_attributes)

    provider = _get_provider()
    logger = provider.get_logger(__name__)

    logger.emit(
        LogRecord(
            timestamp=int(_time.time_ns()),
            severity_text="INFO" if ok else "ERROR",
            severity_number=SeverityNumber.INFO if ok else SeverityNumber.ERROR,
            body=f"agent tool call: {tool_name}",
            attributes=attributes,
            event_name="gen_ai.tool.call",
        )
    )


# Configure logfire eagerly on import (no-op when logfire is not installed).
_CONFIGURED_LOGFIRE = _configure_logfire()
