#!/usr/bin/env python3
"""Ship Zed agent tool-call metadata to LocalObserve.

Zed persists native agent threads as zstd-compressed JSON in threads.db. This
observer reads that database without modifying it, checkpoints existing history,
and polls for tool calls in new or updated threads. Prompts, completions,
thinking, and tool outputs are never exported; tool names and arguments are
retained as detection signals, matching the existing AI-agent privacy model.
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import zstandard
from opentelemetry._logs import LogRecord
from opentelemetry._logs.severity import SeverityNumber
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

from agent_otel_prelude import otlp_http_endpoint

LOG = logging.getLogger("zed_agent_observer")
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = REPO_ROOT / ".data" / "agent-sessions" / "zed-observer-state.json"
DEFAULT_DB = (
    Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    / "zed"
    / "threads"
    / "threads.db"
)


@dataclass(frozen=True)
class ToolCall:
    session_id: str
    tool_use_id: str
    name: str
    arguments: str
    status: str
    updated_at: str

    @property
    def is_error(self) -> bool:
        return self.status == "error"

    def timestamp_ns(self) -> int:
        try:
            parsed = datetime.fromisoformat(self.updated_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return int(parsed.timestamp() * 1_000_000_000)
        except (TypeError, ValueError):
            return time.time_ns()

    def attributes(self) -> dict[str, Any]:
        status_code = {"completed": "OK", "error": "ERROR"}.get(self.status, "UNSET")
        attributes: dict[str, Any] = {
            "gen_ai.tool.name": self.name,
            "gen_ai.tool.args": self.arguments,
            "gen_ai.tool.call.id": self.tool_use_id,
            "gen_ai_tool_name": self.name,
            "gen_ai_tool_args": self.arguments,
            "ai_session_id": self.session_id,
            "ai.agent.name": "zed",
            "ai.capture_prompts": False,
            "otel.status_code": status_code,
            "zed.tool_use_id": self.tool_use_id,
            "zed.tool_status": self.status,
        }
        if self.is_error:
            attributes["error.message"] = "Zed marked this tool call as failed"
        return attributes


class Sink(Protocol):
    def emit(self, call: ToolCall) -> None: ...

    def flush(self) -> bool: ...

    def close(self) -> None: ...


class OtlpSink:
    """Maintain one OTLP logger provider per Zed thread/session."""

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint.rstrip("/")
        self._providers: dict[str, LoggerProvider] = {}
        self._loggers: dict[str, Any] = {}

    def _logger(self, session_id: str):
        if session_id not in self._loggers:
            resource = Resource.create(
                {
                    "service.name": "zed",
                    "service.namespace": "ai-agents",
                    "ai.session.id": session_id,
                    "ai.agent.name": "zed",
                    "ai.capture_prompts": False,
                }
            )
            provider = LoggerProvider(resource=resource)
            provider.add_log_record_processor(
                BatchLogRecordProcessor(
                    OTLPLogExporter(endpoint=f"{self.endpoint}/v1/logs"),
                    schedule_delay_millis=500,
                )
            )
            self._providers[session_id] = provider
            self._loggers[session_id] = provider.get_logger(__name__)
        return self._loggers[session_id]

    def emit(self, call: ToolCall) -> None:
        severity = SeverityNumber.ERROR if call.is_error else SeverityNumber.INFO
        self._logger(call.session_id).emit(
            LogRecord(
                timestamp=call.timestamp_ns(),
                severity_text="ERROR" if call.is_error else "INFO",
                severity_number=severity,
                body=f"agent tool call: {call.name}",
                attributes=call.attributes(),
                event_name="gen_ai.tool.call",
            )
        )

    def flush(self) -> bool:
        results = [
            provider.force_flush(timeout_millis=10_000)
            for provider in self._providers.values()
        ]
        return all(results)

    def close(self) -> None:
        for provider in self._providers.values():
            provider.shutdown()
        self._providers.clear()
        self._loggers.clear()


def _tool_arguments(tool_use: dict[str, Any]) -> str:
    tool_input = tool_use.get("input")
    value = tool_input.get("value") if isinstance(tool_input, dict) else None
    if value is None and tool_use.get("raw_input"):
        try:
            raw = json.loads(tool_use["raw_input"])
            value = raw.get("value", raw) if isinstance(raw, dict) else raw
        except (json.JSONDecodeError, TypeError):
            value = tool_use["raw_input"]
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "" if value is None else str(value)


def extract_tool_calls(session_id: str, thread: dict[str, Any], updated_at: str) -> list[ToolCall]:
    """Extract only tool metadata from Zed's versioned native-thread JSON."""
    messages = thread.get("messages", [])
    if not isinstance(messages, list):
        return []

    results: dict[str, dict[str, Any]] = {}
    for message in messages:
        agent = message.get("Agent") if isinstance(message, dict) else None
        if not isinstance(agent, dict) or not isinstance(agent.get("tool_results"), dict):
            continue
        for key, result in agent["tool_results"].items():
            if isinstance(result, dict):
                results[str(result.get("tool_use_id") or key)] = result

    calls: list[ToolCall] = []
    seen: set[str] = set()
    for message in messages:
        agent = message.get("Agent") if isinstance(message, dict) else None
        content = agent.get("content", []) if isinstance(agent, dict) else []
        if not isinstance(content, list):
            continue
        for block in content:
            tool_use = block.get("ToolUse") if isinstance(block, dict) else None
            if not isinstance(tool_use, dict):
                continue
            tool_use_id = str(tool_use.get("id") or "")
            if not tool_use_id or tool_use_id in seen:
                continue
            seen.add(tool_use_id)
            result = results.get(tool_use_id)
            if result is None:
                status = "running"
            elif result.get("is_error"):
                status = "error"
            else:
                status = "completed"
            calls.append(
                ToolCall(
                    session_id=session_id,
                    tool_use_id=tool_use_id,
                    name=str(tool_use.get("name") or "unknown"),
                    arguments=_tool_arguments(tool_use),
                    status=status,
                    updated_at=updated_at,
                )
            )
    return calls


class ZedAgentObserver:
    def __init__(
        self, db_path: Path, state_path: Path, sink: Sink, *, backfill_existing: bool = False
    ) -> None:
        self.db_path = db_path
        self.state_path = state_path
        self.sink = sink
        self.backfill_existing = backfill_existing
        self.state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"version": 1, "baseline_complete": False, "threads": {}}
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        if state.get("version") != 1 or not isinstance(state.get("threads"), dict):
            raise ValueError(f"unsupported observer state in {self.state_path}")
        return {
            "version": 1,
            "baseline_complete": bool(state.get("baseline_complete", False)),
            "threads": state["threads"],
        }

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.replace(self.state_path)

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Zed thread database not found: {self.db_path}")
        connection = sqlite3.connect(f"{self.db_path.as_uri()}?mode=ro", uri=True, timeout=5)
        connection.execute("PRAGMA query_only = ON")
        return connection

    @staticmethod
    def _decode_thread(data_type: str, data: bytes) -> dict[str, Any]:
        if data_type == "zstd":
            with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(data)) as reader:
                raw = reader.read()
        elif data_type in {"json", "none"}:
            raw = data
        else:
            raise ValueError(f"unsupported Zed thread encoding: {data_type}")
        thread = json.loads(raw)
        if not isinstance(thread, dict):
            raise ValueError("Zed thread payload is not a JSON object")
        return thread

    def scan(self) -> tuple[int, int]:
        """Process changed threads; return (changed thread count, emitted call count)."""
        changed = 0
        emitted_total = 0
        initial_scan = not self.state["baseline_complete"]
        with self._connect() as connection:
            metadata = connection.execute("SELECT id, updated_at FROM threads").fetchall()
            for session_id, updated_at in metadata:
                previous = self.state["threads"].get(session_id, {})
                if previous.get("updated_at") == updated_at:
                    continue
                row = connection.execute(
                    "SELECT data_type, data FROM threads WHERE id = ?", (session_id,)
                ).fetchone()
                if row is None:
                    continue
                thread = self._decode_thread(row[0], row[1])
                emitted_ids = set(previous.get("emitted_tool_ids", []))
                emitted_this_thread = 0
                checkpointed_this_thread = 0
                # Existing history is checkpointed during the first scan so
                # starting the observer cannot replay thousands of old detections.
                # After the baseline exists, both changed active threads and newly
                # created threads are exported.
                export_calls = (
                    self.backfill_existing or bool(previous) or not initial_scan
                )
                for call in extract_tool_calls(session_id, thread, updated_at):
                    if call.tool_use_id in emitted_ids:
                        continue
                    if export_calls:
                        self.sink.emit(call)
                        emitted_this_thread += 1
                    else:
                        checkpointed_this_thread += 1
                    emitted_ids.add(call.tool_use_id)
                if emitted_this_thread and not self.sink.flush():
                    raise RuntimeError("OTLP export did not flush successfully; will retry")
                self.state["threads"][session_id] = {
                    "updated_at": updated_at,
                    "emitted_tool_ids": sorted(emitted_ids),
                }
                self._save_state()
                changed += 1
                emitted_total += emitted_this_thread
                LOG.info(
                    "thread %s: exported %d new tool calls; checkpointed %d existing calls",
                    session_id,
                    emitted_this_thread,
                    checkpointed_this_thread,
                )
        self.state["baseline_complete"] = True
        self._save_state()
        return changed, emitted_total

    def run(self, poll_interval: float) -> None:
        while True:
            try:
                self.scan()
            except Exception:
                LOG.exception("Zed observer scan failed; retrying")
            time.sleep(poll_interval)

    def close(self) -> None:
        self.sink.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Zed threads.db path")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE, help="checkpoint JSON path")
    parser.add_argument("--endpoint", default=otlp_http_endpoint(), help="OTLP/HTTP base endpoint")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="poll seconds")
    parser.add_argument("--once", action="store_true", help="scan once and exit")
    parser.add_argument(
        "--backfill-existing",
        action="store_true",
        help="export pre-existing tool history instead of only checkpointing it",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.poll_interval <= 0:
        raise SystemExit("--poll-interval must be greater than zero")
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    observer = ZedAgentObserver(
        args.db, args.state, OtlpSink(args.endpoint), backfill_existing=args.backfill_existing
    )
    try:
        if args.once:
            changed, emitted = observer.scan()
            LOG.info("scan complete: %d changed threads, %d tool calls", changed, emitted)
        else:
            LOG.info(
                "watching %s; exporting tool metadata to %s/v1/logs",
                args.db,
                args.endpoint,
            )
            observer.run(args.poll_interval)
    finally:
        observer.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
