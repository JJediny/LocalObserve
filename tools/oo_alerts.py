#!/usr/bin/env python3
"""
oo_alerts.py: Helper backend for oo-alerts.sh implementing OpenObserve alert rules GitOps.
"""

import os
import sys
import json
import urllib.request
import urllib.error
import base64

OPENOBSERVE_URL = os.environ.get("OPENOBSERVE_URL", "http://localhost:5080")
USERNAME = os.environ.get("ZO_ROOT_USER_EMAIL", os.environ.get("OPENOBSERVE_USERNAME", "root@example.com"))
PASSWORD = os.environ.get("ZO_ROOT_USER_PASSWORD", os.environ.get("OPENOBSERVE_PASSWORD", "Complexpass#123"))
ORG = os.environ.get("OPENOBSERVE_ORG", "default")
ALERTS_FILE = "alerts/openobserve/alerts.json"


def get_auth_header():
    auth_str = f"{USERNAME}:{PASSWORD}"
    auth_b64 = base64.b64encode(auth_str.encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {auth_b64}"}


def make_request(url, method="GET", data=None, headers=None):
    if headers is None:
        headers = {}
    headers.update(get_auth_header())
    
    req_data = None
    if data is not None:
        req_data = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
        
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            resp_body = res.read().decode("utf-8")
            if resp_body:
                return json.loads(resp_body)
            return {}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        print(f"HTTP Error {e.code} for {method} {url}: {error_body}", file=sys.stderr)
        raise
    except Exception as e:
        print(f"Network error for {method} {url}: {e}", file=sys.stderr)
        raise


def list_existing_alerts():
    url = f"{OPENOBSERVE_URL}/api/v2/{ORG}/alerts"
    try:
        res = make_request(url)
        return res.get("list", [])
    except Exception:
        print("Failed to list active alerts from OpenObserve.", file=sys.stderr)
        sys.exit(1)


def list_destinations():
    url = f"{OPENOBSERVE_URL}/api/{ORG}/alerts/destinations"
    try:
        return make_request(url)
    except Exception:
        print("Failed to list alert destinations from OpenObserve.", file=sys.stderr)
        sys.exit(1)


def setup_destination():
    print("Checking for existing 'localhost-webhook' destination...")
    destinations = list_destinations()
    exists = any(d.get("name") == "localhost-webhook" for d in destinations)
    if exists:
        print("Destination 'localhost-webhook' already configured.")
        return
        
    print("Registering 'localhost-webhook' destination pointing to the webhook receiver container...")
    url = f"{OPENOBSERVE_URL}/api/{ORG}/alerts/destinations"
    payload = {
        "name": "localhost-webhook",
        "type": "http",
        "url": "http://alert-receiver:9000/hooks/security-alert-open",
        "method": "post",
        "template": "Default"
    }
    try:
        make_request(url, method="POST", data=payload)
        print("Successfully created 'localhost-webhook' destination.")
    except Exception as e:
        print(f"Failed to create webhook destination: {e}", file=sys.stderr)
        sys.exit(1)


def export_alerts():
    print(f"Querying all configured alerts in organization '{ORG}'...")
    alert_list = list_existing_alerts()
    print(f"Found {len(alert_list)} alert rules in list. Fetching full details for each...")
    
    clean_alerts = []
    for item in alert_list:
        alert_id = item.get("alert_id") or item.get("id")
        if not alert_id:
            continue
            
        print(f"Fetching details for alert '{item.get('name')}' (ID: {alert_id})...")
        url = f"{OPENOBSERVE_URL}/api/v2/{ORG}/alerts/{alert_id}"
        try:
            alert = make_request(url)
        except Exception as e:
            print(f"Failed to fetch details for alert ID {alert_id}: {e}", file=sys.stderr)
            continue
            
        # Standardize "system_logs" to "system-logs" for static compliance schema compatibility
        stream_type = alert.get("stream_type")
        if stream_type == "system_logs":
            stream_type = "system-logs"
            
        real_stream_name = alert.get("stream_name")
        if real_stream_name == "system_logs":
            real_stream_name = "system-logs"
            
        qcond = alert.get("query_condition")
        if qcond and qcond.get("sql"):
            qcond = dict(qcond)
            qcond["sql"] = qcond["sql"].replace('"system_logs"', '"system-logs"')

        clean_alert = {
            "name": alert.get("name"),
            "stream_type": stream_type,
            "stream_name": real_stream_name,
            "is_real_time": alert.get("is_real_time", False),
            "query_condition": qcond,
            "trigger_condition": alert.get("trigger_condition"),
            "destinations": alert.get("destinations", ["localhost-webhook"]),
            "template": alert.get("template", ""),
            "context_attributes": alert.get("context_attributes", {}),
            "enabled": alert.get("enabled", True),
            "description": alert.get("description", ""),
            "row_template": alert.get("row_template", ""),
            "row_template_type": alert.get("row_template_type", "String"),
            "folder_id": alert.get("folder_id", "default"),
            "creates_incident": alert.get("creates_incident", False)
        }
        clean_alerts.append(clean_alert)
        
    os.makedirs(os.path.dirname(ALERTS_FILE), exist_ok=True)
    with open(ALERTS_FILE, "w", encoding="utf-8") as f:
        json.dump(clean_alerts, f, indent=2, ensure_ascii=False)
    print(f"Successfully exported alert definitions to: {ALERTS_FILE}")


def import_alerts():
    if not os.path.exists(ALERTS_FILE):
        print(f"Alert configuration file not found at: {ALERTS_FILE}", file=sys.stderr)
        sys.exit(1)
        
    with open(ALERTS_FILE, "r", encoding="utf-8") as f:
        file_alerts = json.load(f)
        
    print(f"Loaded {len(file_alerts)} alert definitions from: {ALERTS_FILE}")
    existing_alerts = list_existing_alerts()
    existing_map = {a.get("name"): (a.get("alert_id") or a.get("id")) for a in existing_alerts if a.get("name")}
    
    # Pre-create the destination to ensure import doesn't fail on missing targets
    setup_destination()
    
    for alert in file_alerts:
        name = alert.get("name")
        if not name:
            continue
            
        # Map "system-logs" to "system_logs" for OpenObserve engine
        payload = dict(alert)
        if payload.get("stream_name") == "system-logs":
            payload["stream_name"] = "system_logs"
            if "query_condition" in payload and payload["query_condition"]:
                qcond = dict(payload["query_condition"])
                if qcond.get("sql"):
                    qcond["sql"] = qcond["sql"].replace('"system-logs"', '"system_logs"')
                payload["query_condition"] = qcond
                
        alert_id = existing_map.get(name)
        if alert_id:
            print(f"Updating alert '{name}' (ID: {alert_id})...")
            url = f"{OPENOBSERVE_URL}/api/v2/{ORG}/alerts/{alert_id}"
            payload["id"] = alert_id
            try:
                make_request(url, method="PUT", data=payload)
            except Exception as e:
                print(f"Failed to update alert '{name}': {e}", file=sys.stderr)
        else:
            print(f"Creating new alert '{name}'...")
            url = f"{OPENOBSERVE_URL}/api/v2/{ORG}/alerts"
            try:
                make_request(url, method="POST", data=payload)
            except Exception as e:
                print(f"Failed to create alert '{name}': {e}", file=sys.stderr)
                
    print("GitOps alert sync import operation completed successfully.")


def main():
    if len(sys.argv) < 2:
        print("Usage: oo_alerts.py export|import|setup-destination")
        sys.exit(1)
        
    command = sys.argv[1]
    if command == "export":
        export_alerts()
    elif command == "import":
        import_alerts()
    elif command == "setup-destination":
        setup_destination()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
