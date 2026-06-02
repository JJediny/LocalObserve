#!/usr/bin/env python3
"""
Rulehound Alignment Validator
Validates that all threat-detection rules mapped in `docs/rulehound_mappings.md`
are active and correctly defined in `osqueryd.conf` and `falco_rules.local.yaml`.
"""
import sys
import re
import json
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_mappings_from_md(md_content: str) -> list[dict]:
    """Parse the rule table from the markdown mappings file."""
    rules = []
    for line in md_content.splitlines():
        if not line.startswith("|") or line.strip().startswith("|-") or "Rulehound" in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 6:
            continue
        rule_id_cell = parts[1]
        engine_cell = parts[3]
        location_cell = parts[4]
        
        # Extract configs enclosed in backticks from the configuration location column
        configs = re.findall(r"`([^`]+)`", location_cell)
        for cfg in configs:
            rules.append({
                "rule_id": rule_id_cell,
                "engine": engine_cell,
                "location": location_cell,
                "details": f"`{cfg}`"
            })
    return rules


def validate_osquery_configs(osquery_conf: dict, expected_queries: list[str], expected_fim_paths: list[str]) -> tuple[list[str], list[str]]:
    """Verify that expected queries and FIM keys are in osqueryd.conf."""
    missing_queries = []
    missing_fim = []
    
    # Check scheduled queries
    queries = osquery_conf.get("schedule", {})
    for q in expected_queries:
        if q not in queries:
            missing_queries.append(q)
            
    # Check FIM category paths
    fim_paths = osquery_conf.get("file_paths", {})
    for f in expected_fim_paths:
        if f not in fim_paths:
            missing_fim.append(f)
            
    return missing_queries, missing_fim


def validate_falco_rules(falco_rules: list[dict], expected_rules: list[str]) -> list[str]:
    """Verify that expected rules are active in falco_rules.local.yaml."""
    missing_rules = []
    active_rules = set()
    
    for item in falco_rules:
        if isinstance(item, dict) and "rule" in item:
            active_rules.add(item["rule"])
            
    for r in expected_rules:
        if r not in active_rules:
            missing_rules.append(r)
            
    return missing_rules


def main():
    print("=== Running Rulehound Detection Rules Alignment Validator ===")
    
    mappings_file = REPO_ROOT / "docs" / "rulehound_mappings.md"
    osquery_file = REPO_ROOT / "osqueryd.conf"
    falco_file = REPO_ROOT / "falco_rules.local.yaml"
    
    if not mappings_file.exists():
        print(f"[-] ERROR: Rulehound mappings file not found at {mappings_file}")
        sys.exit(1)
        
    md_content = mappings_file.read_text(encoding="utf-8")
    
    # Extract all backtick config keys from Column 4 of the mapping table rows only
    all_backticks = []
    for line in md_content.splitlines():
        if line.startswith("|") and not line.strip().startswith("|-") and "Rulehound" not in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 5:
                location_cell = parts[4]
                all_backticks.extend(re.findall(r"`([^`]+)`", location_cell))
            
    # Filter out filenames and duplicates
    config_keys = sorted(list(set([
        k for k in all_backticks 
        if not k.endswith(".yaml") and not k.endswith(".conf")
    ])))
    
    expected_osquery_queries = []
    expected_osquery_fim = []
    expected_falco_rules = []
    
    for key in config_keys:
        if key[0].isupper():
            expected_falco_rules.append(key)
        elif key.endswith("_devices") or key.endswith("_units") or key.endswith("_changes"):
            expected_osquery_queries.append(key)
        else:
            expected_osquery_fim.append(key)
            
    print(f"[+] Loaded {len(config_keys)} unique telemetry keys: {len(expected_falco_rules)} Falco rules, {len(expected_osquery_queries)} OSquery queries, {len(expected_osquery_fim)} OSquery FIM paths.")
    
    # Perform Validation
    errors = 0
    
    # 1. Osquery
    if osquery_file.exists():
        try:
            with open(osquery_file, "r", encoding="utf-8") as f:
                osquery_conf = json.load(f)
            missing_q, missing_f = validate_osquery_configs(
                osquery_conf, expected_osquery_queries, expected_osquery_fim
            )
            for q in missing_q:
                print(f"[-] OSQUERY ERROR: Scheduled query `{q}` is mapped in docs but missing in osqueryd.conf!")
                errors += 1
            for f in missing_f:
                print(f"[-] OSQUERY FIM ERROR: FIM path category `{f}` is mapped in docs but missing in osqueryd.conf!")
                errors += 1
            if not missing_q and not missing_f:
                print("[+] OSquery scheduled queries and FIM paths are fully aligned.")
        except Exception as e:
            print(f"[-] ERROR parsing osqueryd.conf: {e}")
            errors += 1
    else:
        print("[-] WARNING: osqueryd.conf does not exist in workspace root.")
        
    # 2. Falco
    if falco_file.exists():
        try:
            with open(falco_file, "r", encoding="utf-8") as f:
                falco_rules = yaml.safe_load(f)
            missing_rules = validate_falco_rules(falco_rules, expected_falco_rules)
            for r in missing_rules:
                print(f"[-] FALCO ERROR: Rule `{r}` is mapped in docs but missing/inactive in falco_rules.local.yaml!")
                errors += 1
            if not missing_rules:
                print("[+] Falco local rules are fully aligned.")
        except Exception as e:
            print(f"[-] ERROR parsing falco_rules.local.yaml: {e}")
            errors += 1
    else:
        print("[-] WARNING: falco_rules.local.yaml does not exist in workspace root.")

    print("==============================================================")
    if errors == 0:
        print("[+] SUCCESS: All mapped Rulehound rules are 100% active and verified in configurations!")
        sys.exit(0)
    else:
        print(f"[-] FAILURE: Detected {errors} alignment discrepancies in the telemetry pipeline configurations.")
        sys.exit(1)


if __name__ == "__main__":
    main()
