#!/usr/bin/env python3
"""
magika_prescan.py: Google Magika AI File-Type Pre-Scan Hook for ClamAV
Optimizes file auditing and reduces ClamAV CPU overhead by skipping benign media formats.
"""

import os
import sys
import json
import time
import base64
import subprocess
import urllib.request
from pathlib import Path
from magika import Magika

# OpenObserve credentials and configuration
OO_URL = os.environ.get("OPENOBSERVE_URL", "http://localhost:5080/api/default/magika_scans/_json")
OO_USER = os.environ.get("ZO_ROOT_USER_EMAIL", os.environ.get("OPENOBSERVE_USERNAME", "root@example.com"))
OO_PASS = os.environ.get("ZO_ROOT_USER_PASSWORD", os.environ.get("OPENOBSERVE_PASSWORD", "Complexpass#123"))

# Define high-risk groups and content types that ClamAV MUST scan
HIGH_RISK_GROUPS = {"executable", "archive", "script"}
HIGH_RISK_TYPES = {
    "elf", "pe", "macho", "exe", "dll", "so", "python", "bash", "sh", "javascript",
    "typescript", "zip", "tar", "gzip", "bzip2", "rar", "7z", "pdf", "html", "xml"
}

def ship_audit_log(event: dict) -> None:
    """Send pre-scan decision audit log to OpenObserve."""
    try:
        token = base64.b64encode(f"{OO_USER}:{OO_PASS}".encode("utf-8")).decode("ascii")
        req = urllib.request.Request(
            OO_URL,
            data=json.dumps(event).encode("utf-8"),
            headers={
                "Authorization": f"Basic {token}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            pass
    except Exception as e:
        print(f"[-] OpenObserve Audit Log Delivery Failed: {e}", file=sys.stderr)

def scan_file_with_clamav(file_path: Path) -> dict:
    """Run clamdscan via socket for high-risk files."""
    config_path = "/tmp/clamd.conf"
    if not os.path.exists(config_path):
        # Create standard local socket client config if missing
        with open(config_path, "w") as f:
            f.write("LocalSocket /tmp/clamd.sock\n")

    cmd = ["clamdscan", "-c", config_path, "--fdpass", str(file_path)]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        # ClamAV exit codes: 0 = No virus, 1 = Virus found, 2 = Error
        virus_found = completed.returncode == 1
        return {
            "exit_code": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "virus_found": virus_found,
            "success": completed.returncode in (0, 1)
        }
    except Exception as e:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
            "virus_found": False,
            "success": False
        }

def process_file(file_path: Path, magika: Magika) -> None:
    """Classify file type using Magika, decide whether to bypass or scan with ClamAV."""
    if not file_path.exists():
        print(f"[-] File not found: {file_path}", file=sys.stderr)
        return

    if not file_path.is_file():
        return

    # Use Magika to determine true file type
    try:
        result = magika.identify_path(file_path)
        pred = result.prediction
        ct_label = pred.output.label
        group = pred.output.group
        score = pred.score
    except Exception as e:
        print(f"[-] Magika classification failed for {file_path}: {e}", file=sys.stderr)
        ct_label = "unknown"
        group = "unknown"
        score = 0.0

    # Determine risk category
    is_high_risk = (
        group in HIGH_RISK_GROUPS or 
        ct_label in HIGH_RISK_TYPES or 
        group == "unknown" or 
        ct_label == "unknown"
    )

    decision = "scan" if is_high_risk else "whitelist"
    clamav_result = None

    if is_high_risk:
        print(f"[!] SCAN: {file_path} identified as {ct_label} ({group}, score: {score:.2f}) -> Invoking ClamAV.")
        clamav_result = scan_file_with_clamav(file_path)
        if clamav_result["virus_found"]:
            print(f"[CRITICAL] VIRUS FOUND in {file_path}!")
        elif clamav_result["success"]:
            print(f"[+] Scan clean for {file_path}.")
        else:
            print(f"[-] ClamAV scan failed for {file_path}: {clamav_result['stderr']}", file=sys.stderr)
    else:
        print(f"[+] WHITELIST: {file_path} identified as {ct_label} ({group}, score: {score:.2f}) -> Bypassing ClamAV.")

    # Build auditing payload
    event = {
        "timestamp": int(time.time() * 1_000_000),
        "file_path": str(file_path),
        "file_size": file_path.stat().st_size if file_path.exists() else 0,
        "magika_type": ct_label,
        "magika_group": group,
        "magika_score": score,
        "decision": decision,
        "clamav_scanned": is_high_risk,
        "clamav_virus_found": clamav_result["virus_found"] if clamav_result else False,
        "clamav_success": clamav_result["success"] if clamav_result else True,
        "clamav_exit_code": clamav_result["exit_code"] if clamav_result else None
    }

    ship_audit_log(event)

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: magika_prescan.py <file_path1> [file_path2 ...]", file=sys.stderr)
        sys.exit(1)

    magika = Magika()
    for path_str in sys.argv[1:]:
        process_file(Path(path_str), magika)

if __name__ == "__main__":
    main()
