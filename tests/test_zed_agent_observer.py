from __future__ import annotations

import io
import json
import sqlite3
import sys
from pathlib import Path

import zstandard

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from zed_agent_observer import ToolCall, ZedAgentObserver, extract_tool_calls


class MemorySink:
    def __init__(self) -> None:
        self.calls: list[ToolCall] = []

    def emit(self, call: ToolCall) -> None:
        self.calls.append(call)

    def flush(self) -> bool:
        return True

    def close(self) -> None:
        pass


def encode_thread(thread: dict) -> bytes:
    compressor = zstandard.ZstdCompressor()
    buffer = io.BytesIO()
    with compressor.stream_writer(buffer, closefd=False) as stream:
        stream.write(json.dumps(thread).encode())
    return buffer.getvalue()


def write_thread(
    db_path: Path, session_id: str, updated_at: str, thread: dict, *, replace: bool = False
) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS threads "
            "(id TEXT PRIMARY KEY, updated_at TEXT, data_type TEXT, data BLOB)"
        )
        verb = "REPLACE" if replace else "INSERT"
        connection.execute(
            f"{verb} INTO threads VALUES (?, ?, 'zstd', ?)",
            (session_id, updated_at, encode_thread(thread)),
        )


def native_thread(*tool_ids: str) -> dict:
    content = [
        {"Text": "private response text"},
        *[
            {
                "ToolUse": {
                    "id": tool_id,
                    "name": "read_file",
                    "input": {"type": "object", "value": {"path": f"/workspace/{tool_id}.py"}},
                }
            }
            for tool_id in tool_ids
        ],
    ]
    return {
        "messages": [
            {"User": {"content": [{"Text": "private prompt"}]}},
            {
                "Agent": {
                    "content": content,
                    "tool_results": {
                        tool_id: {
                            "tool_use_id": tool_id,
                            "is_error": tool_id == "failed",
                            "output": "private tool output",
                        }
                        for tool_id in tool_ids
                    },
                }
            },
        ]
    }


def test_extracts_tool_metadata_without_prompt_or_output() -> None:
    calls = extract_tool_calls("session", native_thread("completed", "failed"), "2026-10-30T00:00:00Z")

    assert [call.tool_use_id for call in calls] == ["completed", "failed"]
    assert [call.status for call in calls] == ["completed", "error"]
    serialized = json.dumps([call.attributes() for call in calls])
    assert "private prompt" not in serialized
    assert "private response text" not in serialized
    assert "private tool output" not in serialized
    assert "/workspace/completed.py" in serialized
    assert calls[1].attributes()["otel.status_code"] == "ERROR"


def test_checkpoints_history_and_captures_active_and_new_threads(tmp_path: Path) -> None:
    db_path = tmp_path / "threads.db"
    state_path = tmp_path / "state.json"
    write_thread(db_path, "active", "2026-10-30T00:00:00Z", native_thread("one"))
    sink = MemorySink()
    observer = ZedAgentObserver(db_path, state_path, sink)

    assert observer.scan() == (1, 0)
    assert sink.calls == []
    assert observer.scan() == (0, 0)

    write_thread(
        db_path,
        "active",
        "2026-10-30T00:01:00Z",
        native_thread("one", "two"),
        replace=True,
    )
    write_thread(db_path, "new", "2026-10-30T00:02:00Z", native_thread("three"))

    assert observer.scan() == (2, 2)
    assert [call.tool_use_id for call in sink.calls] == ["two", "three"]

    restarted_sink = MemorySink()
    restarted = ZedAgentObserver(db_path, state_path, restarted_sink)
    assert restarted.scan() == (0, 0)
    assert restarted_sink.calls == []


def test_explicit_backfill_and_failed_flush_retry(tmp_path: Path) -> None:
    db_path = tmp_path / "threads.db"
    state_path = tmp_path / "state.json"
    write_thread(db_path, "active", "2026-10-30T00:00:00Z", native_thread("one"))
    sink = MemorySink()
    sink.flush = lambda: False
    observer = ZedAgentObserver(db_path, state_path, sink, backfill_existing=True)

    try:
        observer.scan()
    except RuntimeError as error:
        assert "will retry" in str(error)
    else:
        raise AssertionError("failed export should not be checkpointed")
    assert not state_path.exists()
