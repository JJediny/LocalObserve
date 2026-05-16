import json
import os

def create_dashboard(title, description, panels):
    return {
        "v1": None, "v2": None, "v3": None, "v4": None,
        "v5": {
            "version": 5,
            "title": title,
            "description": description,
            "owner": "root@example.com",
            "tabs": [
                {
                    "tabId": "default",
                    "name": "Default",
                    "panels": panels
                }
            ],
            "variables": {"list": [], "showDynamicFilters": True}
        },
        "v6": None, "v7": None, "v8": None
    }

def panel_base(id, title, type, x, y, w, h):
    return {
        "id": f"Panel_{id}",
        "type": type,
        "title": title,
        "layout": {"x": x, "y": y, "w": w, "h": h, "i": id}
    }

# Falco Panels
falco_panels = [
    {
        **panel_base(1, "Alerts by Priority", "pie", 0, 0, 12, 10),
        "queryType": "sql",
        "queries": [{
            "query": "SELECT priority, count(*) as count FROM falco GROUP BY priority",
            "fields": {"stream": "falco", "stream_type": "logs"}
        }]
    },
    {
        **panel_base(2, "Top Triggered Rules", "bar", 12, 0, 36, 10),
        "queryType": "sql",
        "queries": [{
            "query": "SELECT rule, count(*) as count FROM falco GROUP BY rule ORDER BY count DESC LIMIT 10",
            "fields": {"stream": "falco", "stream_type": "logs"}
        }]
    },
    {
        **panel_base(3, "Security Events Over Time", "line", 0, 10, 48, 10),
        "queryType": "sql",
        "queries": [{
            "query": "SELECT histogram(_timestamp, '1m') as time, count(*) as count FROM falco GROUP BY time",
            "fields": {"stream": "falco", "stream_type": "logs"}
        }]
    }
]

# Osquery Panels
osquery_panels = [
    {
        **panel_base(1, "Events by Query", "pie", 0, 0, 12, 10),
        "queryType": "sql",
        "queries": [{
            "query": "SELECT name, count(*) as count FROM osquery GROUP BY name",
            "fields": {"stream": "osquery", "stream_type": "logs"}
        }]
    },
    {
        **panel_base(2, "Recent Activity", "table", 12, 0, 36, 10),
        "queryType": "sql",
        "queries": [{
            "query": "SELECT _timestamp, name, action, host_identifier FROM osquery ORDER BY _timestamp DESC LIMIT 100",
            "fields": {"stream": "osquery", "stream_type": "logs"}
        }]
    }
]

# OTEL Panels
otel_panels = [
    {
        **panel_base(1, "Export Errors", "line", 0, 0, 24, 10),
        "queryType": "promql",
        "queries": [{
            "query": "sum(rate(otelcol_exporter_send_failed_log_records[1m])) by (exporter)",
            "fields": {"stream": "metrics", "stream_type": "metrics"}
        }]
    },
    {
        **panel_base(2, "Collector Memory", "line", 24, 0, 24, 10),
        "queryType": "promql",
        "queries": [{
            "query": "otelcol_process_memory_rss",
            "fields": {"stream": "metrics", "stream_type": "metrics"}
        }]
    }
]

os.makedirs("dashboards/openobserve", exist_ok=True)

with open("dashboards/openobserve/Falco_Security.json", "w") as f:
    json.dump(create_dashboard("Falco Security", "Monitoring Falco security events", falco_panels), f, indent=2)

with open("dashboards/openobserve/Osquery_Events.json", "w") as f:
    json.dump(create_dashboard("Osquery Events", "Tracking system audits via osquery", osquery_panels), f, indent=2)

with open("dashboards/openobserve/OTEL_Collector.json", "w") as f:
    json.dump(create_dashboard("OTEL Collector Health", "Collector performance and export metrics", otel_panels), f, indent=2)
