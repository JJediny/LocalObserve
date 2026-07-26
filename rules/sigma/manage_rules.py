#!/usr/bin/env python3
import os
import sys
import shutil
import subprocess
from pathlib import Path
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
RULES_DIR = SCRIPT_DIR / "rules"
ACTIVE_RULES_DIR = SCRIPT_DIR / "active_rules"
CONFIG_FILE = SCRIPT_DIR / "curated_rules.yaml"
RSIGMA_BINARY = REPO_ROOT / "rsigma"

def load_config():
    if not CONFIG_FILE.exists():
        print(f"Error: curation config {CONFIG_FILE} not found.", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_FILE, "r") as f:
        return yaml.safe_load(f)

def clean_active_dir():
    if ACTIVE_RULES_DIR.exists():
        shutil.rmtree(ACTIVE_RULES_DIR)
    ACTIVE_RULES_DIR.mkdir(parents=True, exist_ok=True)

def process_rules(config):
    curation = config.get("curation", {})
    disabled_rules = curation.get("disabled_rules", [])
    enabled_rules = curation.get("enabled_rules", [])
    tweaks = {t["id"]: t["override"] for t in curation.get("tweaks", []) if "id" in t}

    disabled_ids = set()
    disabled_tags = set()
    for item in disabled_rules:
        if isinstance(item, dict):
            if "id" in item:
                disabled_ids.add(item["id"])
            if "tags" in item:
                disabled_tags.update(item["tags"])

    # Source local rules
    rule_files = list(RULES_DIR.glob("**/*.yml")) + list(RULES_DIR.glob("**/*.yaml"))
    
    compiled_count = 0
    skipped_count = 0

    for rule_path in rule_files:
        try:
            with open(rule_path, "r") as f:
                rule_data = yaml.safe_load(f)
        except Exception as e:
            print(f"Warning: Failed to parse {rule_path}: {e}", file=sys.stderr)
            continue

        if not rule_data or not isinstance(rule_data, dict):
            continue

        rule_id = rule_data.get("id")
        rule_tags = rule_data.get("tags", [])
        if not isinstance(rule_tags, list):
            rule_tags = [rule_tags]

        # Check if disabled
        is_disabled = False
        if rule_id in disabled_ids:
            is_disabled = True
        elif any(tag in disabled_tags for tag in rule_tags):
            is_disabled = True

        if is_disabled:
            skipped_count += 1
            continue

        # Apply tweaks
        if rule_id in tweaks:
            print(f"Applying overrides/tweaks to rule {rule_id} ({rule_data.get('title')})")
            for key, val in tweaks[rule_id].items():
                rule_data[key] = val

        # Write to active rules directory
        output_path = ACTIVE_RULES_DIR / rule_path.name
        with open(output_path, "w") as f:
            yaml.dump(rule_data, f, default_flow_style=False)
        compiled_count += 1

    print(f"Rule Compilation Summary: Compiled {compiled_count} rules, skipped {skipped_count} rules.")

def validate_rules():
    if not RSIGMA_BINARY.exists():
        print("Warning: rsigma binary not found. Skipping validation.", file=sys.stderr)
        return

    print("Validating active rules with rsigma...")
    # Validate rules inside the active_rules folder
    # Note: rsigma rule validate takes rule files or directories
    result = subprocess.run(
        [str(RSIGMA_BINARY), "rule", "validate", str(ACTIVE_RULES_DIR)],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print("Validation failed!", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        print(result.stdout)
        sys.exit(result.returncode)
    else:
        print("All active rules successfully validated!")

def main():
    print("Initializing LocalObserve Sigma Curation Engine...")
    config = load_config()
    clean_active_dir()
    process_rules(config)
    validate_rules()

if __name__ == "__main__":
    main()
