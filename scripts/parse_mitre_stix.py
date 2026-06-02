#!/usr/bin/env python3
"""
MITRE ATT&CK STIX 2.1 Catalog Parser & CSV Generator
Downloads the official enterprise-attack.json, parses all attack-patterns,
and outputs a clean CSV lookup table for OpenObserve alert enrichment.
"""
import os
import sys
import csv
import json
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STIX_URL = "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json"
CACHE_DIR = REPO_ROOT / ".data" / "mitre"
CACHE_FILE = CACHE_DIR / "enterprise-attack.json"
OUTPUT_CSV = REPO_ROOT / "alerts" / "openobserve" / "mitre_lookup.csv"

def download_stix_dataset(url: str, dest: Path, force: bool = False) -> bool:
    """Download the MITRE STIX JSON dataset with a local caching mechanism."""
    if dest.exists() and not force:
        print(f"[+] Using cached MITRE STIX dataset: {dest}")
        return True

    print(f"[*] Downloading MITRE STIX dataset from {url}...")
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        req = urllib.request.Request(
            url, 
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=60) as response:
            with open(dest, "wb") as f:
                f.write(response.read())
        print(f"[+] Download complete. Saved to: {dest}")
        return True
    except Exception as e:
        print(f"[-] ERROR: Failed to download MITRE STIX dataset: {e}", file=sys.stderr)
        return False

def parse_stix_to_csv(stix_file: Path, output_file: Path) -> None:
    """Parse STIX JSON attack-patterns and compile a flat, optimized CSV lookup table."""
    print(f"[*] Parsing STIX catalog from {stix_file}...")
    
    try:
        with open(stix_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[-] ERROR: Failed to read STIX JSON: {e}", file=sys.stderr)
        sys.exit(1)

    objects = data.get("objects", [])
    techniques_count = 0
    
    # Standardize column headers for reference tables
    headers = ["mitre_id", "name", "tactic", "description", "url"]
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(output_file, "w", encoding="utf-8", newline="") as csv_f:
            writer = csv.writer(csv_f)
            writer.writerow(headers)
            
            for obj in objects:
                # We are only interested in attack-pattern (Techniques and Sub-techniques)
                if obj.get("type") != "attack-pattern":
                    continue
                
                # Check for revoked or deprecated objects
                if obj.get("revoked", False) or obj.get("x_mitre_deprecated", False):
                    continue

                # 1. Resolve canonical Technique ID and URL
                mitre_id = None
                url = None
                for ref in obj.get("external_references", []):
                    if ref.get("source_name") == "mitre-attack":
                        mitre_id = ref.get("external_id")
                        url = ref.get("url")
                        break
                
                if not mitre_id:
                    continue

                # 2. Extract Technique Name
                name = obj.get("name", "")

                # 3. Resolve ATT&CK Tactics
                tactics = []
                for phase in obj.get("kill_chain_phases", []):
                    if phase.get("kill_chain_name") == "mitre-attack":
                        tactics.append(phase.get("phase_name").replace("-", " ").title())
                tactic_str = "|".join(tactics)

                # 4. Clean and compact the description
                description = obj.get("description", "")
                if description:
                    # Take the first paragraph and strip code markdowns or newlines
                    first_para = description.split("\n\n")[0].strip()
                    cleaned_desc = first_para.replace("\n", " ").replace("\r", "")
                    # Shorten to maintain high-performance CSV index bounds
                    if len(cleaned_desc) > 220:
                        cleaned_desc = cleaned_desc[:217] + "..."
                    description = cleaned_desc

                # Write record to CSV
                writer.writerow([mitre_id, name, tactic_str, description, url])
                techniques_count += 1
                
        print(f"[+] Successfully extracted {techniques_count} MITRE techniques to: {output_file}")
    except Exception as e:
        print(f"[-] ERROR: Failed to write CSV mapping: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="MITRE ATT&CK STIX Parser to CSV")
    parser.add_argument("--force", action="store_true", help="Force redownload of the STIX JSON catalog")
    args = parser.parse_args()

    # Create directories
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Download/Check caching
    if download_stix_dataset(STIX_URL, CACHE_FILE, force=args.force):
        # Step 2: Parse and generate CSV mapping
        parse_stix_to_csv(CACHE_FILE, OUTPUT_CSV)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
