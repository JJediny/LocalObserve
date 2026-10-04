#!/usr/bin/env python3
"""trigger_alerts.py - Safe, innocent security alert trigger runner for LocalObserve.

Triggers detection alerts across Falco, OSquery, ClamAV, RSigma, and AI Agent
observability using benign, non-destructive commands. Validates stream ingestion
in OpenObserve and webhook dispatch in alert-receiver, and optionally triggers
native Linux desktop notifications.

Usage:
  python3 tools/trigger_alerts.py --all
  python3 tools/trigger_alerts.py --all --notify
  python3 tools/trigger_alerts.py --stream falco
  python3 tools/trigger_alerts.py --stream osquery
  python3 tools/trigger_alerts.py --stream clamav
  python3 tools/trigger_alerts.py --stream agent
  python3 tools/trigger_alerts.py --stream rsigma
  python3 tools/trigger_alerts.py --stream system-logs
  python3 tools/trigger_alerts.py --verify
  python3 tools/trigger_alerts.py --notify
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Default endpoints and credentials
OO_URL = os.environ.get("OPENOBSERVE_URL", "http://localhost:5080")
OO_USER = os.environ.get("ZO_ROOT_USER_EMAIL", "root@example.com")
OO_PASS = os.environ.get("ZO_ROOT_USER_PASSWORD", "Complexpass#123")
RSIGMA_URL = os.environ.get("RSIGMA_URL", "http://localhost:9090")
ALERT_RECEIVER_URL = os.environ.get("ALERT_RECEIVER_URL", "http://localhost:9000")


def _oo_auth_header() -> dict[str, str]:
    auth = base64.b64encode(f"{OO_USER}:{OO_PASS}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}


def _query_oo(stream: str, query_sql: str | None = None, minutes: int = 15, limit: int = 5) -> list[dict]:
    """Execute SQL query against OpenObserve search endpoint."""
    now_us = int(time.time()) * 1_000_000
    sql = query_sql or f'SELECT * FROM "{stream}" ORDER BY _timestamp DESC LIMIT {limit}'
    payload = {
        "query": {
            "sql": sql,
            "start_time": now_us - minutes * 60 * 1_000_000,
            "end_time": now_us,
        }
    }
    req = urllib.request.Request(
        f"{OO_URL}/api/default/_search",
        data=json.dumps(payload).encode(),
        headers=_oo_auth_header(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            res = json.loads(r.read())
            return res.get("hits", [])
    except Exception as e:
        print(f"[-] OpenObserve search failed for stream '{stream}': {e}", file=sys.stderr)
        return []


def _post_json(url: str, data: dict | list, headers: dict[str, str] | None = None) -> tuple[int, str]:
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers=hdrs,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode() if e.fp else str(e)
    except Exception as e:
        return 0, str(e)


# ---------------------------------------------------------------------------
# Individual Stream Triggers (All Non-Destructive & Innocent)
# ---------------------------------------------------------------------------


def trigger_falco() -> bool:
    """Trigger Falco detections using safe, innocent commands."""
    print("\n--- [1/6] Triggering Falco Alerts ---")
    success = True

    # 1. Read sensitive file (safe read of pwquality.conf) -> Read sensitive file untrusted / Falco-High-Severity
    try:
        print("[+] 1.1 Read Sensitive File (Innocent read of /etc/security/pwquality.conf)")
        with open("/etc/security/pwquality.conf", "r") as f:
            _ = f.read(10)
        print("    -> Trigger executed successfully")
    except Exception as e:
        print(f"    [-] Trigger failed: {e}")
        success = False

    # 2. Execution from /tmp (benign /bin/true copied and executed) -> Execution from Temporary Directory
    try:
        print("[+] 1.2 Temp Directory Execution (Copying and running /bin/true in /tmp)")
        tmp_bin = Path("/tmp/innocent_alert_test_bin")
        subprocess.run(["cp", "/bin/true", str(tmp_bin)], check=True)
        subprocess.run([str(tmp_bin)], check=True)
        tmp_bin.unlink(missing_ok=True)
        print("    -> Trigger executed and cleaned up successfully")
    except Exception as e:
        print(f"    [-] Trigger failed: {e}")
        success = False

    # 3. LD_PRELOAD injection (loading standard benign libc) -> Hijack Execution Flow with LD_PRELOAD
    try:
        print("[+] 1.3 LD_PRELOAD Environment Hook (Preloading standard libc.so.6 on benign true)")
        libc_path = "/lib/x86_64-linux-gnu/libc.so.6"
        if os.path.exists(libc_path):
            env = os.environ.copy()
            env["LD_PRELOAD"] = libc_path
            subprocess.run(["true"], env=env, check=True)
            print("    -> Trigger executed successfully")
        else:
            print(f"    [*] Notice: {libc_path} not found on this arch, skipping LD_PRELOAD")
    except Exception as e:
        print(f"    [-] Trigger failed: {e}")
        success = False

    return success


def trigger_osquery() -> bool:
    """Trigger OSquery alerts by triggering FIM and recording monitored events."""
    print("\n--- [2/6] Triggering OSquery Alerts ---")
    success = True

    # 1. FIM file modification on monitored bashrc
    try:
        print("[+] 2.1 FIM File Update (Touching user ~/.bashrc)")
        bashrc = Path.home() / ".bashrc"
        if bashrc.exists():
            bashrc.touch()
            print("    -> Touched ~/.bashrc successfully")
    except Exception as e:
        print(f"    [-] Failed touching ~/.bashrc: {e}")

    # 2. FIM touch inside osquery container if running
    try:
        print("[+] 2.2 FIM Container File Touch (/root/.bashrc inside container)")
        res = subprocess.run(
            ["docker", "exec", "localobserve-osquery-1", "touch", "/root/.bashrc"],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            print("    -> Container FIM trigger executed successfully")
        else:
            print(f"    [*] Notice: container touch returned {res.returncode}: {res.stderr.strip()}")
    except Exception as e:
        print(f"    [*] Notice: docker exec skipped ({e})")

    # 3. Synthetic detection events in osquery results log for instant pipeline validation
    try:
        print("[+] 2.3 OSquery Telemetry Results Event (Crontab & SUID changes)")
        log_file = REPO_ROOT / ".data" / "osquery" / "osqueryd.results.log"
        if not log_file.exists():
            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_file.touch()

        # Fix permissions if container root created it
        try:
            subprocess.run(
                ["docker", "exec", "localobserve-osquery-1", "chmod", "666", "/var/log/osquery/osqueryd.results.log"],
                capture_output=True,
            )
        except Exception:
            pass

        now_str = time.asctime(time.gmtime())
        now_ts = int(time.time())

        events = [
            {
                "name": "crontab",
                "command": "curl -s http://localhost:5080/healthz",
                "columns": {
                    "command": "curl -s http://localhost:5080/healthz",
                    "path": "/var/spool/cron/crontabs/testuser",
                },
                "action": "added",
                "hostIdentifier": "localhost",
                "calendarTime": now_str,
                "unixTime": now_ts,
            },
            {
                "name": "file_events",
                "action": "UPDATED",
                "columns": {
                    "target_path": "/home/john/.bashrc",
                    "action": "UPDATED",
                },
                "hostIdentifier": "localhost",
                "calendarTime": now_str,
                "unixTime": now_ts,
            },
            {
                "name": "suid_bin_changes",
                "action": "added",
                "columns": {
                    "path": "/tmp/innocent_suid_test",
                    "permissions": "4755",
                },
                "hostIdentifier": "localhost",
                "calendarTime": now_str,
                "unixTime": now_ts,
            },
        ]
        with open(log_file, "a") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")
        print("    -> Appended crontab, file_events, and suid_bin_changes telemetry to osquery log")
    except Exception as e:
        print(f"    [-] Appending osquery events failed: {e}")
        success = False

    return success


def trigger_clamav() -> bool:
    """Trigger ClamAV alert by logging benign EICAR test scan result."""
    print("\n--- [3/6] Triggering ClamAV Alerts ---")
    try:
        clamav_log = REPO_ROOT / ".data" / "clamav" / "scan.log"
        clamav_log.parent.mkdir(parents=True, exist_ok=True)
        # EICAR detection line conforming to collector regex
        line = "/tmp/innocent_eicar_test.com: FOUND Win.Test.EICAR_HDB-1\n"
        with open(clamav_log, "a") as f:
            f.write(line)
        print("[+] Logged harmless EICAR test detection to .data/clamav/scan.log")
        return True
    except Exception as e:
        print(f"[-] ClamAV trigger failed: {e}")
        return False


def trigger_agent() -> bool:
    """Trigger AI Agent observability alerts via synthetic tool calls."""
    print("\n--- [4/6] Triggering AI Agent Observability Alerts ---")
    try:
        demo_script = REPO_ROOT / "tools" / "agent_session_demo.py"
        venv_py = REPO_ROOT / ".venv" / "bin" / "python"
        uv_bin = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")

        if venv_py.exists():
            cmd = [str(venv_py), str(demo_script), "--quick"]
        elif os.path.exists(uv_bin):
            cmd = [uv_bin, "run", "python", str(demo_script), "--quick"]
        else:
            cmd = [sys.executable, str(demo_script), "--quick"]

        res = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        print(res.stdout.strip())
        if res.returncode == 0:
            print("[+] Emitted AI agent tool telemetry (sensitive file read + error call)")
            return True
        else:
            print(f"[-] AI agent demo exited with code {res.returncode}: {res.stderr}")
            return False
    except Exception as e:
        print(f"[-] AI Agent trigger failed: {e}")
        return False


def trigger_rsigma() -> bool:
    """Trigger RSigma streaming Sigma detections."""
    print("\n--- [5/6] Triggering RSigma Real-Time Detections ---")
    success = True
    test_events = [
        {
            "name": "unshare",
            "cmdline": "unshare --user --map-root-user /bin/bash",
            "pid": 88000 + int(time.time()) % 1000,
        },
        {
            "service_namespace": "agent",
            "gen_ai_tool_name": "read_file",
            "gen_ai_tool_args": "/etc/shadow",
            "pid": 89000 + int(time.time()) % 1000,
        },
        {
            "service_namespace": "agent",
            "gen_ai_tool_name": "run_shell",
            "gen_ai_tool_args": "rm -rf /",
            "pid": 90000 + int(time.time()) % 1000,
        },
    ]

    for ev in test_events:
        status, resp = _post_json(f"{RSIGMA_URL}/api/v1/events", ev)
        rule_hint = ev.get("name") or ev.get("gen_ai_tool_name")
        if status == 200:
            print(f"[+] RSigma event accepted ({rule_hint}): {resp.strip()}")
        else:
            print(f"[-] RSigma event rejected ({rule_hint}): HTTP {status} {resp.strip()}")
            success = False

    return success


def trigger_system_logs() -> bool:
    """Trigger SystemLogs auth failure and sudo alerts via OpenObserve ingest."""
    print("\n--- [6/6] Triggering SystemLogs Alerts ---")
    logs = [
        {
            "message": "sshd[99123]: Failed password for invalid user admin from 192.168.1.100 port 55123 ssh2",
            "facility": "auth",
            "hostname": "localobserve-test",
        },
        {
            "message": "sudo: guest_user : TTY=pts/3 ; PWD=/tmp ; USER=root ; COMMAND=/bin/cat /etc/shadow",
            "facility": "authpriv",
            "hostname": "localobserve-test",
        },
    ]
    status, resp = _post_json(
        f"{OO_URL}/api/default/system_logs/_json",
        logs,
        headers=_oo_auth_header(),
    )
    if status == 200:
        print(f"[+] System logs ingested successfully into system_logs stream: {resp.strip()}")
        return True
    else:
        print(f"[-] System logs ingestion failed: HTTP {status} {resp.strip()}")
        return False


# ---------------------------------------------------------------------------
# Verification Engine & Desktop Notification Replay
# ---------------------------------------------------------------------------


def replay_desktop_notifications() -> None:
    """Invoke host-side desktop notifier to replay queued alert popups via notify-send."""
    print("\n--- Triggering Native Desktop Notifications (notify-send) ---")
    notifier_script = REPO_ROOT / "tools" / "desktop_notifier.py"
    if notifier_script.exists():
        try:
            res = subprocess.run(
                [sys.executable, str(notifier_script), "--replay", "--once"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=15,
            )
            print(res.stdout.strip())
            if res.returncode == 0:
                print("[✔] Desktop notifications successfully dispatched via notify-send")
            else:
                print(f"[!] Desktop notifier exited with code {res.returncode}: {res.stderr.strip()}")
        except Exception as e:
            print(f"[-] Failed executing desktop notifier: {e}")
    else:
        print("[-] tools/desktop_notifier.py not found")


def verify_all(minutes: int = 15) -> dict[str, int]:
    """Verify detection events across all OpenObserve streams and webhook receiver."""
    print("\n=======================================================")
    print(f"Verifying Ingested Telemetry Across Streams (Last {minutes}m)")
    print("=======================================================")

    results = {}
    streams = {
        "falco": 'SELECT count(*) as cnt FROM "falco"',
        "clamav": 'SELECT count(*) as cnt FROM "clamav"',
        "agent_logs": 'SELECT count(*) as cnt FROM "agent_logs"',
        "system_logs": 'SELECT count(*) as cnt FROM "system_logs"',
        "osquery": 'SELECT count(*) as cnt FROM "osquery"',
    }

    for s, sql in streams.items():
        hits = _query_oo(s, query_sql=sql, minutes=minutes)
        cnt = hits[0].get("cnt", 0) if hits else 0
        results[s] = cnt
        status_icon = "✔" if cnt > 0 else "✘"
        print(f"  [{status_icon}] Stream '{s:<12}': {cnt:>6} hits")

    # Check alert-receiver alerts directory
    print("\n--- Verifying Alert Receiver Dispatches ---")
    try:
        proc = subprocess.run(
            ["docker", "exec", "localobserve-alert-receiver-1", "ls", "-1", "/var/log/alerts"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        alert_files = [f for f in proc.stdout.splitlines() if f.endswith(".json")]
        print(f"  [✔] Alert-Receiver dispatched alerts: {len(alert_files)} files in /var/log/alerts")
        if alert_files:
            latest = alert_files[-1]
            cat_proc = subprocess.run(
                ["docker", "exec", "localobserve-alert-receiver-1", "cat", f"/var/log/alerts/{latest}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            print(f"      Latest alert ({latest}):\n{cat_proc.stdout.strip()}")
    except Exception as e:
        print(f"  [-] Alert-Receiver check skipped or failed: {e}")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Trigger all innocent security alerts")
    parser.add_argument("--stream", choices=["falco", "osquery", "clamav", "agent", "rsigma", "system-logs"], help="Trigger specific stream")
    parser.add_argument("--verify", action="store_true", help="Verify ingestion counts in OpenObserve")
    parser.add_argument("--notify", action="store_true", help="Replay alert backlog to native Linux desktop notifications via notify-send")
    parser.add_argument("--window", type=int, default=15, help="Search time window in minutes for verification")
    args = parser.parse_args()

    if not (args.all or args.stream or args.verify or args.notify):
        parser.print_help()
        return 1

    if args.all or args.stream == "falco":
        trigger_falco()
    if args.all or args.stream == "osquery":
        trigger_osquery()
    if args.all or args.stream == "clamav":
        trigger_clamav()
    if args.all or args.stream == "agent":
        trigger_agent()
    if args.all or args.stream == "rsigma":
        trigger_rsigma()
    if args.all or args.stream == "system-logs":
        trigger_system_logs()

    # Allow pipelines 3s to process and ship logs
    if args.all or args.stream:
        print("\nWaiting 3 seconds for OpenTelemetry Collector and OpenObserve to process...")
        time.sleep(3)

    if args.all or args.verify:
        verify_all(minutes=args.window)

    if args.all or args.notify:
        replay_desktop_notifications()

    return 0


if __name__ == "__main__":
    sys.exit(main())
