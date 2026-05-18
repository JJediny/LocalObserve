#!/usr/bin/env python3
import json
import csv
import urllib.request
import urllib.parse
import os
import base64

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OSQUERY_CONF = os.path.join(PROJECT_ROOT, 'osqueryd.conf')
STIX_FILE = os.path.join(PROJECT_ROOT, '.data/mitre_cti/enterprise-attack.json')
CSV_FILE = os.path.join(PROJECT_ROOT, '.data/mitre_cti/mitre_lookup.csv')

# 1. Update OSQuery config with MITRE tags
with open(OSQUERY_CONF, 'r') as f:
    conf = json.load(f)

mitre_map = {
    'crontab': 'T1053.003',
    'crontab_changes': 'T1053.003',
    'systemd_units': 'T1543.002',
    'startup_items': 'T1547',
    'suid_bin': 'T1548.001',
    'sudo_users': 'T1548.003',
    'kernel_modules': 'T1547.006',
    'hidden_processes': 'T1564.001',
    'listening_ports': 'T1071',
    'file_changes': 'T1565.001',
    'users': 'T1136.001',
    'authorized_keys': 'T1098.004',
    'docker_containers': 'T1610'
}

for qname, qdata in conf.get('schedule', {}).items():
    if qname in mitre_map:
        tag = mitre_map[qname]
        desc = qdata.get('description', '')
        if f"[{tag}]" not in desc:
            qdata['description'] = f"{desc} [{tag}]"

with open(OSQUERY_CONF, 'w') as f:
    json.dump(conf, f, indent=2)

print("[*] Added MITRE tags to OSquery configuration.")

# 2. Parse STIX JSON and create Enrichment CSV
print("[*] Parsing STIX JSON for OpenObserve Enrichment...")
if not os.path.exists(STIX_FILE):
    print("STIX JSON not found. Run fetch_mitre_stix.sh first.")
    exit(1)

with open(STIX_FILE, 'r') as f:
    stix_data = json.load(f)

mitre_lookup = {}
for obj in stix_data.get('objects', []):
    if obj.get('type') == 'attack-pattern':
        ext_refs = obj.get('external_references', [])
        mitre_id = next((ref['external_id'] for ref in ext_refs if ref.get('source_name') == 'mitre-attack' and ref.get('external_id')), None)
        if mitre_id:
            mitre_lookup[mitre_id] = {
                'mitre_id': mitre_id,
                'technique': obj.get('name', ''),
                'description': obj.get('description', '').split('\n')[0][:100] + "...", # Truncate description
                'url': next((ref['url'] for ref in ext_refs if ref.get('source_name') == 'mitre-attack' and ref.get('url')), '')
            }

with open(CSV_FILE, 'w', newline='') as csvfile:
    fieldnames = ['mitre_id', 'technique', 'description', 'url']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    for row in mitre_lookup.values():
        writer.writerow(row)

print(f"[*] Generated lookup CSV with {len(mitre_lookup)} techniques at {CSV_FILE}")

# 3. Upload to OpenObserve Enrichment API via curl
# We generate a curl command because Python's urllib multipart upload is tedious
# and curl is guaranteed to work cleanly.
os.system(f'curl -s -u root@example.com:Complexpass#123 -X POST "http://localhost:5080/api/default/enrichment_tables/mitre" -F "file=@{CSV_FILE}"')
print("\n[*] Uploaded MITRE lookup table to OpenObserve.")
