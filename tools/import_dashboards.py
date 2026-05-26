#!/usr/bin/env python3
"""
tools/import_dashboards.py: Dashboard Migration and Import Orchestrator
Migrates version-enveloped OpenObserve dashboard templates to flat, standard v8 JSON
and uploads them programmatically to the live OpenObserve server.
"""

import os
import json
import base64
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_DIR = os.path.join(PROJECT_ROOT, "dashboards", "openobserve")

OO_URL = "http://localhost:5080/api/default/dashboards"
OO_USER = os.environ.get("OPENOBSERVE_USERNAME", "root@example.com")
OO_PASS = os.environ.get("OPENOBSERVE_PASSWORD", "Complexpass#123")

def migrate_and_import():
    token = base64.b64encode(f"{OO_USER}:{OO_PASS}".encode("utf-8")).decode("ascii")
    
    if not os.path.exists(DASHBOARD_DIR):
        print(f"[-] Dashboards directory does not exist: {DASHBOARD_DIR}")
        return

    for filename in os.listdir(DASHBOARD_DIR):
        if not filename.endswith(".json"):
            continue
            
        file_path = os.path.join(DASHBOARD_DIR, filename)
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception as e:
                print(f"[-] Failed to parse {filename}: {e}")
                continue
        
        # Check if it uses the versioned envelope (v1..v8)
        inner_dashboard = None
        for key in ["v8", "v7", "v6", "v5", "v4", "v3", "v2", "v1"]:
            if key in data and data[key] is not None:
                inner_dashboard = data[key]
                break
        
        if inner_dashboard is None:
            # Already a flat structure or unknown, use it directly
            inner_dashboard = data
            
        # Ensure standard keys are set for v8 compliance
        title = inner_dashboard.get("title", filename.replace(".json", ""))
        dashboard_id = inner_dashboard.get("dashboardId", title.lower().replace(" ", "-").replace("_", "-").replace("&", "and"))
        
        inner_dashboard["dashboardId"] = dashboard_id
        inner_dashboard["version"] = 8
        if "description" not in inner_dashboard:
            inner_dashboard["description"] = f"Imported dashboard for {title}"
        if "tabs" not in inner_dashboard:
            inner_dashboard["tabs"] = [{"tabId": "default", "name": "Default", "panels": []}]
        if "variables" not in inner_dashboard:
            inner_dashboard["variables"] = {"list": [], "showDynamicFilters": True}
        if "defaultDatetimeDuration" not in inner_dashboard:
            inner_dashboard["defaultDatetimeDuration"] = {"type": "relative", "relativeTimePeriod": "15m"}
            
        # 1. Overwrite the file with the clean flat JSON schema so the repo templates are completely optimized
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(inner_dashboard, f, indent=2)
        print(f"[+] Migrated and flattened template: {filename}")
        
        # 2. Upload to OpenObserve REST API
        try:
            req = urllib.request.Request(
                OO_URL,
                data=json.dumps(inner_dashboard).encode("utf-8"),
                headers={
                    "Authorization": f"Basic {token}",
                    "Content-Type": "application/json"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as res:
                resp_data = res.read().decode("utf-8")
                print(f"   [+] Uploaded {title} to OpenObserve: {resp_data}")
        except Exception as e:
            # Print any upload warning/error
            print(f"   [-] Failed to upload {title} to OpenObserve: {e}")

if __name__ == "__main__":
    migrate_and_import()
