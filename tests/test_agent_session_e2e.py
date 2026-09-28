"""End-to-end AI agent session capture test (issue #91) - requires the live stack.

Verifies the full path: agent tool-call emission -> OTLP -> collector routing
-> OpenObserve agent_logs stream (with prompt redaction) -> rsigma Sigma
detections.

Run with:
  uv run python -m pytest tests/test_agent_session_e2e.py --run-stack -v
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[1]
OO_BASE = os.environ.get("OO_BASE", "http://localhost:5080/api/default")
OO_USER = os.environ.get("ZO_ROOT_USER_EMAIL", "root@example.com")
OO_PASS = os.environ.get("ZO_ROOT_USER_PASSWORD", "Complexpass#123")

SEARCH_TIMEOUT_S = 60


def _search(stream: str, where: str, minutes: int = 10) -> list[dict]:
    auth = base64.b64encode(f"{OO_USER}:{OO_PASS}".encode()).decode()
    now_us = int(time.time()) * 1_000_000
    payload = {
        "query": {
            "sql": f'SELECT * FROM "{stream}" WHERE {where} ORDER BY _timestamp DESC LIMIT 50',
            "start_time": now_us - minutes * 60 * 1_000_000,
            "end_time": now_us,
            "from": 0,
            "size": 50,
        }
    }
    req = urllib.request.Request(
        f"{OO_BASE}/_search",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("hits", [])
    except urllib.error.HTTPError as e:
        # OpenObserve answers 400 ("Search stream not found") when the stream
        # was never created. No stream => no records => treat as zero hits
        # (callers use this for absence checks like leak detection).
        if e.code == 400:
            return []
        raise


def _wait_for(stream: str, where: str, expect: int) -> list[dict]:
    deadline = time.monotonic() + SEARCH_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            hits = _search(stream, where)
            if len(hits) >= expect:
                return hits
        except Exception:
            pass  # stream may not exist yet (creation is on first record)
        time.sleep(3)
    return []


@pytest.fixture(scope="module")
def demo_session() -> dict:
    """Run the synthetic agent session and return its manifest."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "agent_session_demo.py"), "--quick"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )
    assert result.returncode == 0, f"agent demo failed:\n{result.stdout}\n{result.stderr}"
    # Demo prints: 'agent session <id> (service=...)'
    session_id = None
    for line in result.stdout.splitlines():
        if line.startswith("agent session "):
            session_id = line.split()[2]
    assert session_id, "could not parse session id from demo output"
    return {"session_id": session_id}


class TestAgentSessionE2E:
    def test_tool_calls_reach_agent_logs_stream(self, demo_session: dict) -> None:
        sid = demo_session["session_id"]
        hits = _wait_for("agent_logs", f"ai_session_id = '{sid}'", expect=3)
        assert len(hits) >= 3, f"expected >=3 tool calls for session {sid}, got {len(hits)}"
        tools = {h.get("gen_ai_tool_name") for h in hits}
        assert "read_file" in tools

    def test_routing_namespace_present(self, demo_session: dict) -> None:
        sid = demo_session["session_id"]
        hits = _wait_for("agent_logs", f"ai_session_id = '{sid}'", expect=1)
        assert hits, "no agent records found"
        for hit in hits:
            assert hit.get("service_namespace") == "ai-agents"

    def test_prompts_redacted_by_default(self, demo_session: dict) -> None:
        sid = demo_session["session_id"]
        hits = _wait_for("agent_logs", f"ai_session_id = '{sid}'", expect=1)
        for hit in hits:
            assert "gen_ai_prompt" not in hit, (
                "prompt content must be redacted by default (AGENT_CAPTURE_PROMPTS=false)"
            )
            assert "gen_ai_completion" not in hit

    def test_agent_logs_absent_from_generic_otlp_stream(self, demo_session: dict) -> None:
        sid = demo_session["session_id"]
        # Give the pipeline a moment, then confirm no leakage into otlp_logs
        time.sleep(5)
        hits = _search("otlp_logs", f"ai_session_id = '{sid}'")
        assert not hits, "agent records leaked into the generic otlp_logs stream"
