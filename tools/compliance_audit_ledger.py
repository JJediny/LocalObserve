#!/usr/bin/env python3
"""
compliance_audit_ledger.py: High-integrity, chain-linked audit ledger for telemetry configurations.
Computes SHA-256 hashes of active config files and records them in a tamper-evident audit chain.
Satisfies OMB Memorandum M-26-14 Requirement 5 (Tamper-evident Audit Trail).
"""
import argparse
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_FILE = REPO_ROOT / ".artifacts" / "audit_ledger.json"

CONFIG_FILES = {
    "otel-collector": "otel-collector-config.yaml",
    "falco-config": "falco-config.yaml",
    "falco-rules": "falco_rules.local.yaml",
    "osquery-config": "osqueryd.conf",
}


def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def load_ledger() -> list[dict]:
    if not LEDGER_FILE.exists():
        LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
        return []
    try:
        with open(LEDGER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"WARNING: Failed to read existing ledger: {e}", file=sys.stderr)
        return []


def save_ledger(ledger: list[dict]):
    with open(LEDGER_FILE, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2)


def verify_chain(ledger: list[dict]) -> bool:
    """Validate that every block in the ledger is cryptographically chain-linked."""
    if not ledger:
        return True

    for i, entry in enumerate(ledger):
        # 1. Verify content hash of this entry's block payload
        payload = {
            "index": entry["index"],
            "timestamp": entry["timestamp"],
            "hashes": entry["hashes"],
            "previous_hash": entry["previous_hash"],
        }
        computed_payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()

        if computed_payload_hash != entry["hash"]:
            print(f"CRITICAL: Integrity failure at block {entry['index']}! Hash mismatch.", file=sys.stderr)
            return False

        # 2. Check previous link
        if i > 0:
            if entry["previous_hash"] != ledger[i - 1]["hash"]:
                print(f"CRITICAL: Linkage failure at block {entry['index']}! Previous hash mismatch.", file=sys.stderr)
                return False
        else:
            if entry["previous_hash"] != "0" * 64:
                print("CRITICAL: Genesis block previous hash is invalid.", file=sys.stderr)
                return False

    return True


def audit_and_append() -> int:
    ledger = load_ledger()

    # Verify existing ledger chain
    if not verify_chain(ledger):
        print("CRITICAL: Existing audit ledger is corrupted/tampered!", file=sys.stderr)
        return 1

    # Compute current configs' hashes
    current_hashes = {}
    missing_files = []
    for name, relative_path in CONFIG_FILES.items():
        full_path = REPO_ROOT / relative_path
        if not full_path.exists():
            missing_files.append(str(relative_path))
            continue
        current_hashes[name] = compute_sha256(full_path)

    if missing_files:
        print(f"ERROR: Missing configuration files: {', '.join(missing_files)}", file=sys.stderr)
        return 2

    # Determine previous hash
    prev_hash = "0" * 64
    next_index = 0
    if ledger:
        prev_hash = ledger[-1]["hash"]
        next_index = ledger[-1]["index"] + 1

    # Build next block payload
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    payload = {
        "index": next_index,
        "timestamp": timestamp,
        "hashes": current_hashes,
        "previous_hash": prev_hash,
    }

    # Cryptographically sign/hash this block payload
    computed_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()

    # Append block
    block = payload.copy()
    block["hash"] = computed_hash
    ledger.append(block)

    save_ledger(ledger)
    print(f"Audit ledger block {next_index} committed successfully. Hash: {computed_hash}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="M-26-14 Compliance Config Audit Ledger")
    parser.add_argument("action", choices=["audit", "verify"], default="audit", nargs="?")
    args = parser.parse_args()

    if args.action == "verify":
        ledger = load_ledger()
        if not ledger:
            print("Ledger is empty.")
            return 0
        if verify_chain(ledger):
            print(f"Integrity verified successfully! Chain contains {len(ledger)} valid tamper-evident blocks.")
            return 0
        else:
            return 1
    else:
        return audit_and_append()


if __name__ == "__main__":
    sys.exit(main())
