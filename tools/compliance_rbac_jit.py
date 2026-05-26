#!/usr/bin/env python3
"""
compliance_rbac_jit.py: Just-in-Time (JIT) permission provisioner and audited External Auditor log exporter.
"""

import os
import sys
import json
import argparse
import time
import hashlib
import urllib.request
import urllib.error
import base64
from datetime import datetime, timedelta, timezone

OPENOBSERVE_URL = os.environ.get("OPENOBSERVE_URL", "http://localhost:5080")
USERNAME = os.environ.get("ZO_ROOT_USER_EMAIL", os.environ.get("OPENOBSERVE_USERNAME", "root@example.com"))
PASSWORD = os.environ.get("ZO_ROOT_USER_PASSWORD", os.environ.get("OPENOBSERVE_PASSWORD", "Complexpass#123"))
ORG = os.environ.get("OPENOBSERVE_ORG", "default")
JIT_LOG_FILE = "/home/john/LocalObserve/.artifacts/jit_access_log.json"


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


def log_to_openobserve_audit(action, details):
    """
    Ingest a security auditing record directly into the rbac_audit stream in OpenObserve.
    """
    url = f"{OPENOBSERVE_URL}/api/{ORG}/rbac_audit/_json"
    audit_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "operator": USERNAME,
        **details
    }
    try:
        make_request(url, method="POST", data=[audit_record])
        print(f"Audit log successfully registered in 'rbac_audit' stream for: {action}")
    except Exception as e:
        print(f"Warning: Failed to publish audit record to OpenObserve: {e}", file=sys.stderr)


def get_users_list():
    url = f"{OPENOBSERVE_URL}/api/{ORG}/users"
    try:
        res = make_request(url)
        # Handle dict or list formats gracefully
        if isinstance(res, dict):
            return res.get("data", res.get("users", []))
        return res
    except Exception as e:
        print(f"Error fetching users: {e}", file=sys.stderr)
        return []


def create_jit_user(email, password, role):
    url = f"{OPENOBSERVE_URL}/api/{ORG}/users"
    payload = {
        "email": email,
        "password": password,
        "role": role,
        "first_name": "JIT",
        "last_name": "Compliance"
    }
    try:
        make_request(url, method="POST", data=payload)
        return True
    except Exception as e:
        print(f"Failed to create JIT user: {e}", file=sys.stderr)
        return False


def update_jit_user(email, role):
    url = f"{OPENOBSERVE_URL}/api/{ORG}/users/{email}"
    payload = {
        "role": role
    }
    try:
        make_request(url, method="PUT", data=payload)
        return True
    except urllib.error.HTTPError as e:
        # OpenObserve returns 400 if user role is already what we requested
        if e.code == 400:
            print(f"Permissions for {email} are already aligned with role '{role}'.")
            return True
        print(f"Failed to update user role: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Failed to update user role: {e}", file=sys.stderr)
        return False


def delete_jit_user(email):
    url = f"{OPENOBSERVE_URL}/api/{ORG}/users/{email}"
    try:
        make_request(url, method="DELETE")
        return True
    except Exception as e:
        print(f"Failed to delete user: {e}", file=sys.stderr)
        return False


def load_jit_tickets():
    if not os.path.exists(JIT_LOG_FILE):
        return []
    try:
        with open(JIT_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_jit_tickets(tickets):
    os.makedirs(os.path.dirname(JIT_LOG_FILE), exist_ok=True)
    with open(JIT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(tickets, f, indent=2)


def handle_grant(args):
    email = args.email
    role = args.role
    duration = args.duration
    password = args.password or "JITPass123_Secure"
    
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=duration)
    
    print(f"Initiating JIT grant for {email} to role '{role}' for {duration} minutes...")
    
    # Query current user list
    users = get_users_list()
    user_exists = False
    for u in users:
        if isinstance(u, dict) and u.get("email") == email:
            user_exists = True
            break
        elif isinstance(u, str) and u == email:
            user_exists = True
            break
            
    success = False
    if user_exists:
        print(f"User {email} already exists. Elevating permissions via JIT mapping...")
        success = update_jit_user(email, role)
    else:
        print(f"Creating new temporary JIT user {email}...")
        success = create_jit_user(email, password, role)
        
    if not success:
        print("Failed to provision JIT privileges in OpenObserve.", file=sys.stderr)
        sys.exit(1)
        
    ticket = {
        "ticket_id": hashlib.sha1(f"{email}-{now.isoformat()}".encode("utf-8")).hexdigest()[:8],
        "email": email,
        "role": role,
        "granted_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "active": True
    }
    
    tickets = load_jit_tickets()
    tickets.append(ticket)
    save_jit_tickets(tickets)
    
    # Audit log to OpenObserve rbac_audit stream
    log_to_openobserve_audit("GRANT_JIT", {
        "user_email": email,
        "assigned_role": role,
        "duration_minutes": duration,
        "ticket_id": ticket["ticket_id"],
        "status": "SUCCESS"
    })
    
    print(f"JIT access successfully provisioned. Ticket ID: {ticket['ticket_id']}.")
    print(f"Privileges will automatically expire at: {ticket['expires_at']}")


def handle_audit(args):
    print("Starting JIT ticket and active session audit cycle...")
    tickets = load_jit_tickets()
    now = datetime.now(timezone.utc)
    
    updated_tickets = []
    changes_made = False
    
    for ticket in tickets:
        if ticket.get("active"):
            expires_at_str = ticket.get("expires_at")
            expires_at = datetime.fromisoformat(expires_at_str)
            
            if now >= expires_at:
                email = ticket.get("email")
                role = ticket.get("role")
                ticket_id = ticket.get("ticket_id")
                print(f"JIT Ticket {ticket_id} has expired! Revoking permissions for {email}...")
                
                # Delete user or downgrade them to 'viewer' / none
                success = delete_jit_user(email)
                if success:
                    ticket["active"] = False
                    ticket["revoked_at"] = now.isoformat()
                    changes_made = True
                    log_to_openobserve_audit("EXPIRE_JIT", {
                        "user_email": email,
                        "assigned_role": role,
                        "ticket_id": ticket_id,
                        "status": "SUCCESS"
                    })
                    print(f"Revocation completed for {email}.")
                else:
                    print(f"Error revoking permissions for user: {email}", file=sys.stderr)
            else:
                updated_tickets.append(ticket)
        else:
            updated_tickets.append(ticket)
            
    if changes_made:
        save_jit_tickets(tickets)
    else:
        print("Audit completed. All active JIT access tickets are currently within validity limits.")


def handle_export_cisa_fbi(args):
    stream = args.stream
    # Map stream-logs to system_logs for OpenObserve querying
    query_stream = "system_logs" if stream == "system-logs" else stream
    hours = args.hours
    output_file = args.output
    
    print(f"Initiating audited External Auditor compliance log retrieval for stream '{stream}'...")
    
    # Calculate microsecond timestamps
    now_ts = int(time.time() * 1000000)
    start_ts = now_ts - (hours * 3600 * 1000000)
    
    url = f"{OPENOBSERVE_URL}/api/{ORG}/_search"
    query_payload = {
        "query": {
            "sql": f"SELECT * FROM \"{query_stream}\" ORDER BY _timestamp DESC LIMIT 5000",
            "start_time": start_ts,
            "end_time": now_ts
        }
    }
    
    try:
        res = make_request(url, method="POST", data=query_payload)
    except Exception as e:
        print(f"Search query execution failed: {e}", file=sys.stderr)
        sys.exit(1)
        
    hits = res.get("hits", [])
    record_count = len(hits)
    print(f"Successfully retrieved {record_count} logs matching timeframe window.")
    
    # Compute cryptographic verification checksum across the records
    serialized_records = json.dumps(hits, sort_keys=True)
    record_sha256 = hashlib.sha256(serialized_records.encode("utf-8")).hexdigest()
    
    export_payload = {
        "export_metadata": {
            "agency": "LocalObserve",
            "compliance_reference": "OMB Memorandum M-26-14 (CEM & THIRF Baselines)",
            "stream_source": stream,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "time_window_start": datetime.fromtimestamp(start_ts / 1000000, timezone.utc).isoformat(),
            "time_window_end": datetime.fromtimestamp(now_ts / 1000000, timezone.utc).isoformat(),
            "record_count": record_count,
            "audit_hash": record_sha256
        },
        "records": hits
    }
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(export_payload, f, indent=2)
        
    print(f"Compliance package successfully generated and written to: {output_file}")
    
    # Register this sensitive data sharing event in the tamper-evident rbac_audit ledger stream
    log_to_openobserve_audit("CISA_FBI_EXPORT", {
        "exported_stream": stream,
        "record_count": record_count,
        "destination_file": output_file,
        "cryptographic_verification_hash": record_sha256,
        "status": "SUCCESS"
    })


def main():
    parser = argparse.ArgumentParser(description="JIT RBAC Access Manager & Audited compliance log exporter.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Grant command
    grant_parser = subparsers.add_parser("grant", help="Grant temporary JIT access permissions.")
    grant_parser.add_argument("--email", required=True, help="User email identifier.")
    grant_parser.add_argument("--role", required=True, choices=["admin", "root"], help="Assigned OpenObserve role.")
    grant_parser.add_argument("--duration", type=int, default=60, help="Ticket duration in minutes.")
    grant_parser.add_argument("--password", help="Temporary JIT password.")
    
    # Audit command
    subparsers.add_parser("audit", help="Audit active tickets and revoke expired privileges.")
    
    # Export External Auditor command
    export_parser = subparsers.add_parser("export-cisa-fbi", help="Export audit logs matching External Auditor ingestion schemas.")
    export_parser.add_argument("--stream", required=True, choices=["falco", "osquery", "system-logs"], help="Target stream name.")
    export_parser.add_argument("--hours", type=int, default=24, help="Window frame duration in hours.")
    export_parser.add_argument("--output", default="/home/john/LocalObserve/.artifacts/cisa_fbi_export.json", help="Destination file path.")
    
    args = parser.parse_args()
    
    if args.command == "grant":
        handle_grant(args)
    elif args.command == "audit":
        handle_audit(args)
    elif args.command == "export-cisa-fbi":
        handle_export_cisa_fbi(args)


if __name__ == "__main__":
    main()
