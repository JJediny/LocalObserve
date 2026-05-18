#!/usr/bin/env python3
# tools/correlate_logs.py
#
# Programmatically correlates Falco security alerts with host syslogs and OSquery logs
# by querying the OpenObserve SQL search API.

import json
import urllib.request
import urllib.parse
import base64
import time
import sys

OO_URL = "http://localhost:5080"
OO_ORG = "default"
OO_USER = "root@example.com"
OO_PASS = "Complexpass#123"

# Colors for terminal styling
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

def query_openobserve(sql, start_time, end_time):
    url = f"{OO_URL}/api/{OO_ORG}/_search"
    payload = {
        "query": {
            "sql": sql,
            "start_time": start_time,
            "end_time": end_time
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": b"Basic " + base64.b64encode(f"{OO_USER}:{OO_PASS}".encode("utf-8"))
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as res:
            data = json.load(res)
            return data.get("hits", [])
    except Exception as e:
        print(f"{RED}Error querying OpenObserve: {e}{RESET}", file=sys.stderr)
        return []

def format_ts(micro_ts):
    # Convert microseconds timestamp to readable string
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(micro_ts / 1000000)) + f".{int(micro_ts % 1000000):06d} UTC"

def main():
    print(f"{BOLD}{BLUE}======================================================================{RESET}")
    print(f"{BOLD}{BLUE}🔍 OpenObserve Telemetry Log Correlation Engine{RESET}")
    print(f"{BOLD}{BLUE}======================================================================{RESET}\n")

    # Time range: Last 1 hour
    now = int(time.time() * 1000000)
    start_time = now - 3600 * 1000000
    end_time = now + 60 * 1000000

    print(f"[*] Querying latest Falco alerts from OpenObserve...")
    falco_sql = "SELECT _timestamp, priority, rule, output FROM falco ORDER BY _timestamp DESC LIMIT 10"
    falco_hits = query_openobserve(falco_sql, start_time, end_time)

    if not falco_hits:
        print(f"{YELLOW}No Falco alerts found in the last 1 hour. Run 'task trigger-detections' first!{RESET}")
        return

    print(f"{GREEN}Found {len(falco_hits)} recent Falco alerts.{RESET}\n")

    for i, alert in enumerate(falco_hits):
        ts = alert["_timestamp"]
        rule = alert.get("rule", "Unknown Rule")
        priority = alert.get("priority", "Unknown")
        output = alert.get("output", "")
        
        # Color match based on priority
        color = RED if priority in ["Critical", "Error", "Warning"] else YELLOW
        
        print(f"{BOLD}{BLUE}--- Alert #{i+1}: {rule} ({priority}) ---{RESET}")
        print(f"  {BOLD}Time:{RESET}     {format_ts(ts)}")
        print(f"  {BOLD}Details:{RESET}  {color}{output}{RESET}")
        
        # Define a correlation window (+/- 5 seconds) around the alert
        win_start = ts - 5000000
        win_end = ts + 5000000
        
        # 1. Query correlated syslog entries
        sys_sql = f"SELECT _timestamp, body FROM system_logs WHERE _timestamp BETWEEN {win_start} AND {win_end} ORDER BY _timestamp ASC LIMIT 5"
        sys_hits = query_openobserve(sys_sql, start_time, end_time)
        
        if sys_hits:
            print(f"\n  {BOLD}{GREEN}Correlated Host Syslogs (within +/- 5s window):{RESET}")
            for hit in sys_hits:
                sys_ts = hit["_timestamp"]
                body = hit["body"]
                offset = (sys_ts - ts) / 1000000
                offset_str = f"+{offset:.2f}s" if offset >= 0 else f"{offset:.2f}s"
                print(f"    [{offset_str}] {body}")
        else:
            print(f"\n  {YELLOW}No correlated Host Syslogs found within +/- 5s.{RESET}")

        # 2. Query correlated OSquery results
        osq_sql = f"SELECT _timestamp, name, action, body FROM osquery WHERE _timestamp BETWEEN {win_start} AND {win_end} ORDER BY _timestamp ASC LIMIT 5"
        osq_hits = query_openobserve(osq_sql, start_time, end_time)
        
        if osq_hits:
            print(f"\n  {BOLD}{GREEN}Correlated OSquery Results (within +/- 5s window):{RESET}")
            for hit in osq_hits:
                osq_ts = hit["_timestamp"]
                name = hit["name"]
                action = hit["action"]
                offset = (osq_ts - ts) / 1000000
                offset_str = f"+{offset:.2f}s" if offset >= 0 else f"{offset:.2f}s"
                print(f"    [{offset_str}] Query: {BOLD}{name}{RESET} | Action: {action}")
        else:
            print(f"\n  {YELLOW}No correlated OSquery Results found within +/- 5s.{RESET}")
            
        print(f"\n{BLUE}----------------------------------------------------------------------{RESET}\n")

if __name__ == "__main__":
    main()
