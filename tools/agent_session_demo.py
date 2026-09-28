#!/usr/bin/env python3
"""Synthetic AI agent session for LocalObserve (issue #91).

Runs a scripted agent session that performs four tool calls:
  1. a benign workspace file read (expected: no detection)
  2. a shell command with an innocuous argument (expected: no detection)
  3. a sensitive-file access attempt on /etc/shadow (expected:
     AI Agent Sensitive File Access)
  4. a credential-file read of a .env file (expected:
     AI Agent Credential File Read)

Every tool call is emitted as an OTLP log record via agent_otel_prelude and
land in the OpenObserve `agent-logs` stream, where rsigma evaluates them and
the AI_Agent_Sessions dashboard visualizes them.

Usage:
  uv run python tools/agent_session_demo.py            # full session
  uv run python tools/agent_session_demo.py --quick   # only the two detections

This is also the Part A `agent` benchmark workload
(tools/bench_stack.py --scenario agent) and the fixture for
tests/test_agent_session_e2e.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_otel_prelude as prelude  # noqa: E402


def run_session(quick: bool = False) -> list[dict]:
    """Execute the scripted session; return the emitted events."""
    events: list[dict] = []

    def call(tool: str, args: str, *, expect: str, ok: bool = True, error: str | None = None) -> None:
        prelude.emit_tool_call(tool, args, ok=ok, error=error)
        events.append({"tool": tool, "args": args, "expect": expect})
        print(f"  tool_call: {tool:<14} args={args!r:<55} expect={expect}")

    print(f"agent session {prelude.SESSION_ID} (service={prelude.SERVICE_NAME})")

    if not quick:
        call("read_file", "/home/john/LocalObserve/README.md", expect="clean")
        call("run_shell", "ls -la /home/john/LocalObserve", expect="clean")

    # The two detection-triggering calls (also used by the e2e test):
    call("read_file", "/etc/shadow", expect="AI Agent Sensitive File Access")
    call(
        "read_file",
        "/home/john/LocalObserve/.env",
        expect="AI Agent Credential File Read",
    )

    # An error tool call exercises the error-rate dashboard panel/alert.
    call(
        "run_shell",
        "curl http://example.invalid/",
        expect="clean (error path)",
        ok=False,
        error="connection failed (synthetic)",
    )

    return events


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true", help="only the detection-triggering calls")
    args = ap.parse_args()

    events = run_session(quick=args.quick)

    print(
        f"\nemitted {len(events)} tool calls to {prelude.otlp_http_endpoint()}/v1/logs "
        f"(session {prelude.SESSION_ID})"
    )
    print("verify in OpenObserve:")
    print("  - logs stream 'agent-logs': SELECT * FROM \"agent-logs\" WHERE ai_session_id = '<session>'")
    print("  - dashboard: AI_Agent_Sessions")
    print("  - detections: rsigma should fire the two 'expect:' rules above")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
