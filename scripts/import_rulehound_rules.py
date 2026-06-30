#!/usr/bin/env python3
"""
Rulehound Detection Rule Importer
===================================
Fetches Linux detection rules from the SigmaHQ/sigma repository (the primary
ruleset indexed by Rulehound) and converts them into Falco-compatible YAML
rules that can be directly used by LocalObserve's Falco sidecar.

Usage:
    python scripts/import_rulehound_rules.py [--output rules/rulehound/] [--categories process_creation,file_event]

What it does:
    1. Queries the SigmaHQ GitHub API for Linux rule files in the specified
       categories (default: process_creation, file_event, network_connection).
    2. Downloads each Sigma YAML rule.
    3. Converts Sigma rule definitions into Falco rule YAML format:
       - process_creation -> spawned_process detection
       - file_event       -> open_write / open_read detection
       - network_connection -> outbound detection
    4. Writes the converted Falco rules to rules/rulehound/ as individual YAML files
       and a combined rules/rulehound/rulehound_falco_rules.yaml.

Rulehound (https://github.com/infosecB/Rulehound) is a catalogue of public
threat-detection rulesets. This script uses the Sigma rules it indexes as the
canonical source and translates them into the Falco format LocalObserve uses.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "rules" / "rulehound"

SIGMA_GITHUB_API = "https://api.github.com/repos/SigmaHQ/sigma/contents/rules/linux"
SIGMA_RAW_URL = "https://raw.githubusercontent.com/SigmaHQ/sigma/master/rules/linux"

CATEGORIES = [
    "process_creation",
    "file_event",
    "network_connection",
    "auditd",
    "builtin",
]

# MITRE tag helpers
MITRE_TACTIC_MAP = {
    "attack.defense_evasion": "mitre_defense_evasion",
    "attack.privilege_escalation": "mitre_privilege_escalation",
    "attack.persistence": "mitre_persistence",
    "attack.credential_access": "mitre_credential_access",
    "attack.discovery": "mitre_discovery",
    "attack.lateral_movement": "mitre_lateral_movement",
    "attack.execution": "mitre_execution",
    "attack.exfiltration": "mitre_exfiltration",
    "attack.impact": "mitre_impact",
    "attack.command_and_control": "mitre_command_and_control",
    "attack.initial_access": "mitre_initial_access",
    "attack.collection": "mitre_collection",
}

PRIORITY_MAP = {
    "critical": "CRITICAL",
    "high": "CRITICAL",
    "medium": "WARNING",
    "low": "INFO",
    "informational": "INFO",
}

# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def _github_request(url: str) -> dict | list:
    """Issue a GET request to the GitHub API with optional token auth."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError(f"GitHub API auth error {exc.code} fetching {url}: {exc.reason}") from exc
        print(f"[!] HTTP {exc.code} fetching {url}: {exc.reason}", file=sys.stderr)
        return []


def _fetch_raw(url: str) -> str:
    """Fetch raw text content from a URL."""
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.URLError as exc:
        print(f"[!] Failed to fetch {url}: {exc}", file=sys.stderr)
        return ""


# ---------------------------------------------------------------------------
# Sigma detection block flattening
# ---------------------------------------------------------------------------

def _flatten_detection(detection: dict) -> dict:
    """
    Flatten a Sigma detection block by merging all selection groups
    into a single flat dict. Sigma rules nest detection criteria under
    named selection keys like 'selection', 'filter', etc., while the
    'condition' key describes how they combine.

    This extracts all key-value pairs from nested dicts (except 'condition'
    and other meta-keys) so we can find process names, paths, etc.
    """
    flat: dict[str, list] = {}
    for key, value in detection.items():
        if key == "condition":
            continue
        if isinstance(value, dict):
            for k, v in value.items():
                existing = flat.get(k, [])
                if isinstance(v, list):
                    existing.extend(v)
                else:
                    existing.append(v)
                flat[k] = existing
        elif isinstance(value, list):
            existing = flat.get(key, [])
            existing.extend(value)
            flat[key] = existing
        else:
            existing = flat.get(key, [])
            existing.append(value)
            flat[key] = existing
    return flat


# ---------------------------------------------------------------------------
# Sigma -> Falco conversion
# ---------------------------------------------------------------------------

def _mitre_tags(sigma_tags: list[str]) -> list[str]:
    """Convert Sigma ATT&CK tag notation to Falco-friendly tags."""
    tags: list[str] = []
    for tag in sigma_tags:
        tag_lower = tag.lower()
        if tag_lower in MITRE_TACTIC_MAP:
            tags.append(MITRE_TACTIC_MAP[tag_lower])
        # Extract technique IDs like attack.t1070.002 or attack.t1548.003
        match = re.match(r"attack\.t(\d+\.\d+)", tag_lower)
        if match:
            tags.append(f"T{match.group(1)}")
        else:
            match2 = re.match(r"attack\.t(\d+)$", tag_lower)
            if match2:
                tags.append(f"T{match2.group(1)}")
    tags = list(dict.fromkeys(tags))  # dedupe preserving order
    return tags


def _category_to_falco_event(category: str) -> str:
    """Map a Sigma logsource category to a Falco event macro."""
    mapping = {
        "process_creation": "spawned_process",
        "file_event": "open_write",
        "network_connection": "outbound",
        "auditd": "spawned_process",
        "builtin": "spawned_process",
    }
    return mapping.get(category, "spawned_process")


def _extract_procs(sigma_detection: dict) -> list[str]:
    """
    Extract process/binary names from a Sigma detection block.

    Looks at both top-level and nested (selection group) keys for Image,
    Image|endswith, ProcessName, etc., then filters out wildcards.
    """
    flat = _flatten_detection(sigma_detection)
    procs: list[str] = []
    for key in ("Image", "Image|endswith", "ProcessName", "ProcessName|endswith"):
        vals = flat.get(key, [])
        for v in vals:
            if not isinstance(v, str):
                continue
            basename = v.rsplit("/", 1)[-1] if "/" in v else v
            # Strip leading slash for /rm -> rm
            basename = basename.lstrip("/")
            if basename and not any(c in basename for c in ("*", "?", "%")):
                procs.append(basename)
    return sorted(set(procs))


def _extract_paths(sigma_detection: dict) -> list[str]:
    """
    Extract file/path patterns from a Sigma detection block.

    Looks at TargetFilename, Path, and variants.
    """
    flat = _flatten_detection(sigma_detection)
    paths: list[str] = []
    for key in ("TargetFilename", "TargetFilename|contains", "TargetFilename|endswith",
                "TargetFilename|startswith", "Path", "Path|contains", "Path|endswith"):
        vals = flat.get(key, [])
        for v in vals:
            if isinstance(v, str) and v:
                paths.append(v)
    return sorted(set(paths))


def sigma_to_falco_rule(sigma: dict) -> dict | None:
    """
    Convert a single Sigma rule dict into a Falco rule dict.

    Returns None if the rule cannot be meaningfully converted.
    """
    title = sigma.get("title", "Untitled Sigma Rule")
    description = sigma.get("description", "").strip()
    level = sigma.get("level", "medium")
    tags = _mitre_tags(sigma.get("tags", []))
    logsource = sigma.get("logsource", {})
    category = logsource.get("category", "process_creation")
    detection = sigma.get("detection", {})

    # Use category for the Falco event type
    falco_event = _category_to_falco_event(category)

    procs = _extract_procs(detection)
    paths = _extract_paths(detection)

    # Build condition parts — only add proc_name_exists when there are process conditions
    condition_parts = [falco_event]

    if procs:
        condition_parts.append("proc_name_exists")
        if len(procs) == 1:
            condition_parts.append(f'proc.name = "{procs[0]}"')
        else:
            procs_str = ", ".join(f'"{p}"' for p in procs[:10])  # Limit to avoid overly long rules
            condition_parts.append(f"proc.name in ({procs_str})")

    if paths:
        if len(paths) == 1:
            condition_parts.append(f'fd.name endswith "{paths[0]}"')
        else:
            path_conds = " or ".join(f'fd.name endswith "{p}"' for p in paths[:5])
            condition_parts.append(f"({path_conds})")

    if not procs and not paths:
        # Cannot build a meaningful condition; skip this rule
        return None

    condition = "\n    and ".join(condition_parts)
    priority = PRIORITY_MAP.get(level, "WARNING")
    output = (f"[Rulehound] {title} | user=%user.name command=%proc.cmdline "
              f"process=%proc.name parent=%proc.pname")

    tags.extend(["linux", "rulehound"])
    tags = list(dict.fromkeys(tags))

    rule = {
        "rule": title,
        "desc": description[:300] if description else f"Converted from Sigma rule: {title}",
        "condition": condition,
        "output": output,
        "priority": priority,
        "tags": tags,
    }
    return rule


# ---------------------------------------------------------------------------
# Main import logic
# ---------------------------------------------------------------------------

def fetch_sigma_rules(categories: list[str] | None = None) -> list[dict]:
    """
    Fetch Sigma Linux rules from GitHub and return them as parsed dicts.

    Parameters
    ----------
    categories : list[str] | None
        Sigma rule categories to fetch. Defaults to process_creation and file_event.
    """
    if categories is None:
        categories = ["process_creation", "file_event"]

    all_rules: list[dict] = []

    for cat in categories:
        api_url = f"{SIGMA_GITHUB_API}/{cat}"
        print(f"[*] Fetching Sigma rule index: {cat}")
        entries = _github_request(api_url)
        if not isinstance(entries, list):
            print(f"[!] No entries found for category {cat}, skipping")
            continue

        # Filter for .yml files
        yml_files = [e for e in entries if isinstance(e, dict) and e.get("name", "").endswith(".yml")]
        print(f"[+] Found {len(yml_files)} rules in {cat}")

        for entry in yml_files:
            raw_url = f"{SIGMA_RAW_URL}/{cat}/{entry['name']}"
            content = _fetch_raw(raw_url)
            if not content:
                continue

            try:
                sigma = yaml.safe_load(content)
            except Exception as exc:
                print(f"[!] YAML parse error for {entry['name']}: {exc}", file=sys.stderr)
                continue

            if isinstance(sigma, dict) and "title" in sigma:
                sigma["_category"] = cat
                sigma["_source_file"] = entry["name"]
                all_rules.append(sigma)

    print(f"[+] Total Sigma rules fetched: {len(all_rules)}")
    return all_rules


def convert_and_write(rules: list[dict], output_dir: Path) -> list[Path]:
    """
    Convert Sigma rules to Falco format and write them to output_dir.

    Returns list of written file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    combined: list[dict] = []

    for sigma in rules:
        falco = sigma_to_falco_rule(sigma)
        if falco is None:
            continue

        # Individual file
        safe_name = re.sub(r"[^a-z0-9_]", "_", falco["rule"].lower())[:80]
        out_path = output_dir / f"{safe_name}.yaml"

        with open(out_path, "w", encoding="utf-8") as fh:
            yaml.dump([falco], fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
        written.append(out_path)

        combined.append(falco)

    # Write combined file
    combined_path = output_dir / "rulehound_falco_rules.yaml"
    with open(combined_path, "w", encoding="utf-8") as fh:
        yaml.dump(combined, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)
    written.append(combined_path)

    print(f"[+] Wrote {len(combined)} converted Falco rules and {len(written)} files to {output_dir}")
    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import detection rules from Rulehound (Sigma) and convert to Falco format"
    )
    parser.add_argument(
        "--output", "-o",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory for converted rules (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--categories", "-c",
        default="process_creation,file_event",
        help="Comma-separated Sigma rule categories to fetch (default: process_creation,file_event)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    categories = [c.strip() for c in args.categories.split(",") if c.strip()]

    print("=" * 60)
    print("Rulehound Detection Rule Importer")
    print("=" * 60)
    print(f"  Output directory: {output_dir}")
    print(f"  Categories:      {', '.join(categories)}")
    print()

    # 1. Fetch Sigma rules
    sigma_rules = fetch_sigma_rules(categories)
    if not sigma_rules:
        print("[!] No Sigma rules fetched. Check network connectivity or GitHub API rate limits.", file=sys.stderr)
        return 1

    # 2. Convert and write
    written = convert_and_write(sigma_rules, output_dir)

    print()
    print("[+] Import complete!")
    print(f"    Sigma rules fetched: {len(sigma_rules)}")
    print(f"    Falco rules written: {len(written) - 1}")  # -1 for combined file
    print(f"    Combined rules file: {output_dir / 'rulehound_falco_rules.yaml'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
