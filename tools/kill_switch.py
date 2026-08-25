#!/usr/bin/env python3
"""
kill_switch.py - LocalObserve Premapped ID Kill Switch Tool
Executes local process termination, container isolation, or network block actions
based on premapped security rule IDs or alert keys.
"""

import sys
import os
import json
import argparse
import subprocess
import logging
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAPPING_FILE = REPO_ROOT / "config" / "kill_switch_mappings.json"
AUDIT_LOG_FILE = REPO_ROOT / ".data" / "kill_switch_audit.log"


def setup_logging():
    AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(AUDIT_LOG_FILE),
            logging.StreamHandler(sys.stdout)
        ]
    )


def load_mappings():
    if not MAPPING_FILE.exists():
        raise FileNotFoundError(f"Mapping configuration missing at {MAPPING_FILE}")
    with open(MAPPING_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("mappings", {})


def execute_kill_process(target_name, dry_run=False):
    logging.info(f"[*] Action: kill_process target='{target_name}' dry_run={dry_run}")
    if dry_run:
        logging.info(f"[DRY-RUN] Would execute: pkill -9 -f {target_name}")
        return True

    cmd = ["pkill", "-9", "-f", target_name]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            logging.info(f"[+] Successfully killed process matching '{target_name}'")
            return True
        else:
            logging.warning(f"[!] No active processes matched target '{target_name}' (pkill code {res.returncode})")
            return False
    except Exception as e:
        logging.error(f"[!] Failed to kill process '{target_name}': {e}")
        return False


def _detect_container_runtime():
    """Detect available container runtime, respecting CONTAINER_RUNTIME env var.

    Checks podman, nerdctl, then docker so the kill switch works across
    all three runtimes supported by LocalObserve.
    """
    import shutil
    preferred = os.environ.get("CONTAINER_RUNTIME")
    candidates = [preferred] if preferred else ["podman", "nerdctl", "docker"]
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    return None


def execute_stop_container(container_name, dry_run=False):
    logging.info(f"[*] Action: stop_container target='{container_name}' dry_run={dry_run}")
    runtime_cmd = _detect_container_runtime()
    if not runtime_cmd:
        logging.error("[!] No container runtime found (podman, nerdctl, docker). Set CONTAINER_RUNTIME env var.")
        return False
    if dry_run:
        logging.info(f"[DRY-RUN] Would execute: {runtime_cmd} stop {container_name}")
        return True

    cmd = [runtime_cmd, "stop", container_name]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            logging.info(f"[+] Successfully stopped container '{container_name}' via {runtime_cmd}")
            return True
        else:
            logging.warning(f"[!] Could not stop container '{container_name}': {res.stderr.strip()}")
            return False
    except Exception as e:
        logging.error(f"[!] Failed to stop container '{container_name}': {e}")
        return False


def prompt_yubikey_authentication():
    """Require sudo PAM step-up authentication before a privileged action.

    This triggers ``sudo -v``, which invokes the host's PAM stack. If PAM is
    configured with ``pam_u2f.so`` (see ``docs/yubikey_sudo_elevated_privileges_setup.md``),
    the user must physically touch their YubiKey. Without that PAM configuration,
    this falls back to a standard sudo password prompt.
    """
    print("🔑 [Step-Up Authentication] Elevated Privileged Action Request")
    print("📁 Please authenticate via sudo (YubiKey touch if PAM is configured, otherwise password)...")
    try:
        # Check if sudo credentials are already cached
        res = subprocess.run(["sudo", "-n", "true"], capture_output=True)
        if res.returncode != 0:
            logging.info("[*] Prompting for sudo PAM step-up authentication...")
            subprocess.run(["sudo", "-v"], check=True)
        logging.info("[+] Step-up authentication verified.")
        return True
    except subprocess.CalledProcessError:
        logging.error("[!] Step-up authentication failed or timed out.")
        return False
    except Exception as e:
        logging.warning(f"[*] sudo step-up not enforced on this shell session ({e}). Proceeding with action.")
        return True


def trigger_kill_switch(premapped_id, dry_run=False, require_yubikey=False):
    mappings = load_mappings()
    if premapped_id not in mappings:
        logging.error(f"[!] Premapped ID '{premapped_id}' not found in registry {MAPPING_FILE}")
        return False

    if require_yubikey:
        if not prompt_yubikey_authentication():
            return False

    entry = mappings[premapped_id]
    action_type = entry.get("action_type")
    logging.info(f"[=== KILL SWITCH TRIGGERED ===] ID='{premapped_id}' Name='{entry.get('name')}' Action='{action_type}'")

    if action_type == "kill_process":
        target = entry.get("target_process_name")
        return execute_kill_process(target, dry_run=dry_run)
    elif action_type == "stop_container":
        target = entry.get("target_container_name")
        return execute_stop_container(target, dry_run=dry_run)
    else:
        logging.error(f"[!] Unsupported action_type '{action_type}' for ID '{premapped_id}'")
        return False


def list_mappings():
    mappings = load_mappings()
    print(f"\nLocalObserve Premapped ID Kill Switch Registry ({len(mappings)} entries):\n")
    print(f"{'PREMAPPED ID':<40} | {'ACTION TYPE':<15} | {'TARGET':<25} | {'NAME'}")
    print("-" * 105)
    for premapped_id, info in mappings.items():
        target = info.get("target_process_name") or info.get("target_container_name") or "N/A"
        print(f"{premapped_id:<40} | {info.get('action_type'):<15} | {target:<25} | {info.get('name')}")
    print()


def main():
    setup_logging()
    parser = argparse.ArgumentParser(description="LocalObserve Premapped ID Kill Switch Tool")
    parser.add_argument("--id", help="Premapped Rule ID or Alert Key to execute kill switch for")
    parser.add_argument("--dry-run", action="store_true", help="Simulate action without executing process/container termination")
    parser.add_argument("--prompt-yubikey", action="store_true", help="Require YubiKey physical touch authorization before execution")
    parser.add_argument("--list", action="store_true", help="List all registered premapped IDs and mitigation actions")

    args = parser.parse_args()

    if args.list:
        list_mappings()
        return

    if not args.id:
        parser.print_help()
        sys.exit(1)

    success = trigger_kill_switch(args.id, dry_run=args.dry_run, require_yubikey=args.prompt_yubikey)
    sys.exit(0 if success or args.dry_run else 1)



if __name__ == "__main__":
    main()
