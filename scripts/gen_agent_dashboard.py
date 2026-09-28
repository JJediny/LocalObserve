#!/usr/bin/env python3
"""Generate dashboards/openobserve/AI_Agent_Sessions.json (issue #91 dashboard).

Idempotent: overwrites the dashboard file with the canonical definition.
Run from the repo root: python3 scripts/gen_agent_dashboard.py
"""
import json
from pathlib import Path

OUT = Path("dashboards/openobserve/AI_Agent_Sessions.json")

# NOTE on stream names: the collector exports with `stream-name: agent-logs`,
# but this OpenObserve deployment sanitizes dashes to underscores, so SQL
# must reference "agent_logs". Traces are stored in the "default" traces stream.
AGENT_LOGS = "agent_logs"


def panel(pid, title, ptype, sql, stream, stream_type, layout, extra=None):
    p = {
        "id": f"Panel_{pid}",
        "type": ptype,
        "title": title,
        "layout": layout,
        "queryType": "sql",
        "queries": [
            {
                "query": sql,
                "customQuery": True,
                "fields": {
                    "stream": stream,
                    "stream_type": stream_type,
                    "x": [],
                    "y": [],
                    "z": [],
                    "filter": [],
                },
            }
        ],
    }
    if extra:
        p.update(extra)
    return p


def main() -> int:
    panels = [
        # Row 1: session overview
        panel(
            1,
            "Agent Sessions Over Time",
            "area",
            (
                "SELECT histogram(_timestamp) AS \"x_axis_1\", count(DISTINCT ai_session_id) AS \"y_axis_1\" "
                f'FROM "{AGENT_LOGS}" GROUP BY x_axis_1 ORDER BY x_axis_1'
            ),
            AGENT_LOGS,
            "logs",
            {"x": 0, "y": 0, "w": 12, "h": 10, "i": 1},
        ),
        panel(
            2,
            "Tool Calls by Name",
            "pie",
            (
                "SELECT gen_ai_tool_name AS \"x_axis_1\", count(*) AS \"y_axis_1\" "
                f'FROM "{AGENT_LOGS}" GROUP BY x_axis_1 ORDER BY y_axis_1 DESC'
            ),
            AGENT_LOGS,
            "logs",
            {"x": 12, "y": 0, "w": 6, "h": 10, "i": 2},
        ),
        panel(
            3,
            "Tool Call Errors",
            "bar",
            (
                "SELECT histogram(_timestamp) AS \"x_axis_1\", otel_status_code AS \"x_axis_2\", count(*) AS \"y_axis_1\" "
                f'FROM "{AGENT_LOGS}" GROUP BY x_axis_1, x_axis_2 ORDER BY x_axis_1, x_axis_2'
            ),
            AGENT_LOGS,
            "logs",
            {"x": 18, "y": 0, "w": 6, "h": 10, "i": 3},
        ),
        # Row 2: security focus
        panel(
            4,
            "Sensitive File / Credential Access Attempts",
            "table",
            (
                "SELECT _timestamp, ai_session_id, gen_ai_tool_name, gen_ai_tool_args "
                f'FROM "{AGENT_LOGS}" WHERE '
                "gen_ai_tool_args LIKE '%/etc/shadow%' "
                "OR gen_ai_tool_args LIKE '%/etc/sudoers%' "
                "OR gen_ai_tool_args LIKE '%authorized_keys%' "
                "OR gen_ai_tool_args LIKE '%.aws/credentials%' "
                "OR gen_ai_tool_args LIKE '%.env%' "
                "OR gen_ai_tool_args LIKE '%id_rsa%' "
                "OR gen_ai_tool_args LIKE '%.ssh/id_%' "
                "OR gen_ai_tool_args LIKE '%.kube/config%' "
                "ORDER BY _timestamp DESC LIMIT 100"
            ),
            AGENT_LOGS,
            "logs",
            {"x": 0, "y": 10, "w": 24, "h": 12, "i": 4},
        ),
        panel(
            5,
            "Dangerous Shell Commands by Agents",
            "table",
            (
                "SELECT _timestamp, ai_session_id, gen_ai_tool_args "
                f'FROM "{AGENT_LOGS}" WHERE gen_ai_tool_name LIKE \'%shell%\' AND ('
                "gen_ai_tool_args LIKE '%rm -rf /%' "
                "OR gen_ai_tool_args LIKE '%mkfs%' "
                "OR gen_ai_tool_args LIKE '%dd if=%' "
                "OR gen_ai_tool_args LIKE '%| sh%' "
                "OR gen_ai_tool_args LIKE '%| bash%' "
                "OR gen_ai_tool_args LIKE '%curl%|%' "
                "OR gen_ai_tool_args LIKE '%wget http%') "
                "ORDER BY _timestamp DESC LIMIT 100"
            ),
            AGENT_LOGS,
            "logs",
            {"x": 24, "y": 10, "w": 24, "h": 12, "i": 5},
        ),
        # Row 3: session drill-down
        panel(
            6,
            "Sessions by Agent Service",
            "pie",
            (
                "SELECT service_name AS \"x_axis_1\", count(DISTINCT ai_session_id) AS \"y_axis_1\" "
                f'FROM "{AGENT_LOGS}" GROUP BY x_axis_1 ORDER BY y_axis_1 DESC'
            ),
            AGENT_LOGS,
            "logs",
            {"x": 0, "y": 22, "w": 6, "h": 10, "i": 6},
        ),
        panel(
            7,
            "Recent Agent Tool Calls",
            "table",
            (
                "SELECT _timestamp, ai_session_id, service_name, gen_ai_tool_name, "
                "gen_ai_tool_args, otel_status_code "
                f'FROM "{AGENT_LOGS}" ORDER BY _timestamp DESC LIMIT 100'
            ),
            AGENT_LOGS,
            "logs",
            {"x": 6, "y": 22, "w": 42, "h": 12, "i": 7},
        ),
    ]

    dashboard = {
        "version": 8,
        "dashboardId": "ai-agent-sessions",
        "title": "AI Agent Sessions",
        "description": (
            "AI agent session observability (issue #91): tool calls, errors, and "
            "security-relevant agent activity from the agent_logs stream. Detections "
            "are produced by rsigma (rules/sigma/active_rules/ai_agent_*.yaml)."
        ),
        "owner": "root@example.com",
        "tabs": [
            {
                "tabId": "default",
                "name": "Default",
                "panels": panels,
            }
        ],
        "variables": {
            "list": [
                {
                    "type": "query_values",
                    "name": "service",
                    "label": "Agent Service",
                    "query_data": {
                        "stream_type": "logs",
                        "stream": AGENT_LOGS,
                        "field": "service_name",
                        "max_record_size": None,
                    },
                    "value": "",
                    "options": [],
                },
                {
                    "type": "query_values",
                    "name": "session",
                    "label": "Session ID",
                    "query_data": {
                        "stream_type": "logs",
                        "stream": AGENT_LOGS,
                        "field": "ai_session_id",
                        "max_record_size": None,
                    },
                    "value": "",
                    "options": [],
                },
            ],
            "showDynamicFilters": True,
        },
        "defaultDatetimeDuration": {
            "type": "relative",
            "relativeTimePeriod": "1h",
        },
    }

    OUT.write_text(json.dumps(dashboard, indent=2) + "\n")
    print(f"wrote {OUT} with {len(panels)} panels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
