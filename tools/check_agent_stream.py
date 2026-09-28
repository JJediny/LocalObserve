#!/usr/bin/env python3
"""Quick verification: agent session records in the OpenObserve agent_logs stream.

Usage:
  python3 tools/check_agent_stream.py

NOTE: this older OpenObserve deployment stores the collector's
`stream-name: agent-logs` header as `agent_logs` (underscore-sanitized).
The search uses the POST /_search SQL API with a time window.
"""
import base64
import json
import os
import sys
import time
import urllib.request

BASE = os.environ.get("OO_BASE", "http://localhost:5080/api/default")
USER = os.environ.get("ZO_ROOT_USER_EMAIL", "root@example.com")
PASS = os.environ.get("ZO_ROOT_USER_PASSWORD", "Complexpass#123")

auth = base64.b64encode(f"{USER}:{PASS}".encode()).decode()
HEADERS = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}


def get(path):
    req = urllib.request.Request(f"{BASE}{path}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def post(path, payload):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode(),
        headers=HEADERS,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def search(stream, minutes=30, size=10):
    now_us = int(time.time()) * 1_000_000
    return post(
        "/_search",
        {
            "query": {
                "sql": f'SELECT * FROM "{stream}" ORDER BY _timestamp DESC LIMIT {size}',
                "start_time": now_us - minutes * 60 * 1_000_000,
                "end_time": now_us,
                "from": 0,
                "size": size,
            }
        },
    )


def main():
    streams = get("/streams")
    names = [s["name"] for s in streams.get("list", [])]
    if "agent_logs" not in names:
        print("agent_logs stream NOT FOUND")
        return 1
    print("agent_logs stream: EXISTS")
    logs = search("agent_logs")
    hits = logs.get("hits", [])
    print(f"agent_logs hits: {len(hits)}")
    for h in hits[:8]:
        print(
            json.dumps(
                {
                    "gen_ai_tool_name": h.get("gen_ai_tool_name"),
                    "gen_ai_tool_args": (h.get("gen_ai_tool_args") or "")[:50],
                    "ai_session_id": (h.get("ai_session_id") or "")[:12],
                    "service_namespace": h.get("service_namespace"),
                    "otel_status_code": h.get("otel_status_code"),
                    "gen_ai_prompt": h.get("gen_ai_prompt", "REDACTED/ABSENT"),
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
