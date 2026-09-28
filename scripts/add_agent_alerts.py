#!/usr/bin/env python3
"""Add the two AI-agent alerts to alerts/openobserve/alerts.json (idempotent)."""
import json
from pathlib import Path

ALERTS_PATH = Path("alerts/openobserve/alerts.json")

NEW_ALERTS = [
    {
        "name": "AIAgent-Sensitive-File-Access",
        "stream_type": "logs",
        "stream_name": "agent_logs",
        "is_real_time": False,
        "query_condition": {
            "conditions": None,
            "sql": (
                "SELECT * FROM \"agent_logs\" WHERE (gen_ai_tool_args LIKE '%/etc/shadow%' "
                "OR gen_ai_tool_args LIKE '%/etc/sudoers%' "
                "OR gen_ai_tool_args LIKE '%/etc/ssh/sshd_config%' "
                "OR gen_ai_tool_args LIKE '%authorized_keys%' "
                "OR gen_ai_tool_args LIKE '%/etc/ld.so.preload%')"
            ),
            "promql": "",
            "type": "custom",
            "aggregation": None,
            "promql_condition": None,
            "vrl_function": None,
            "multi_time_range": [],
        },
        "trigger_condition": {
            "period": 1,
            "operator": ">=",
            "frequency": 1,
            "cron": "",
            "threshold": 1,
            "silence": 10,
            "frequency_type": "minutes",
            "timezone": "UTC",
        },
        "destinations": ["localhost-webhook"],
        "template": "",
        "context_attributes": {},
        "enabled": True,
        "description": "AI agent tool call touched a system-critical file (shadow, sudoers, sshd_config, authorized_keys, ld.so.preload) [T1003, T1565.001, T1098.004]",
        "row_template": "",
        "row_template_type": "String",
        "folder_id": "default",
        "creates_incident": False,
    },
    {
        "name": "AIAgent-Tool-Error-Spike",
        "stream_type": "logs",
        "stream_name": "agent_logs",
        "is_real_time": False,
        "query_condition": {
            "conditions": None,
            "sql": (
                "SELECT count(*) as error_count FROM \"agent_logs\" "
                "WHERE otel_status_code = 'ERROR'"
            ),
            "promql": "",
            "type": "custom",
            "aggregation": None,
            "promql_condition": None,
            "vrl_function": None,
            "multi_time_range": [],
        },
        "trigger_condition": {
            "period": 5,
            "operator": ">=",
            "frequency": 5,
            "cron": "",
            "threshold": 5,
            "silence": 30,
            "frequency_type": "minutes",
            "timezone": "UTC",
        },
        "destinations": ["localhost-webhook"],
        "template": "",
        "context_attributes": {},
        "enabled": True,
        "description": "Burst of AI agent tool-call errors (>=5 in 5 min) - possible prompt-injection-driven probing or a broken tool integration",
        "row_template": "",
        "row_template_type": "String",
        "folder_id": "default",
        "creates_incident": False,
    },
]


def main() -> int:
    with ALERTS_PATH.open() as f:
        alerts = json.load(f)
    existing_names = {a["name"] for a in alerts}
    added = 0
    for alert in NEW_ALERTS:
        if alert["name"] not in existing_names:
            alerts.append(alert)
            added += 1
    with ALERTS_PATH.open("w") as f:
        json.dump(alerts, f, indent=2)
        f.write("\n")
    print(f"alerts.json now has {len(alerts)} alerts (added {added})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
