#!/usr/bin/env bash
#
# fetch_mitre_stix.sh
#
# Downloads the latest MITRE ATT&CK Enterprise STIX 2.1 JSON repository
# for use in data source enrichment and coverage mapping.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
STIX_DIR="${PROJECT_ROOT}/.data/mitre_cti"

mkdir -p "$STIX_DIR"

echo "[*] Downloading MITRE ATT&CK Enterprise STIX 2.1 Data..."
curl -s -L -o "${STIX_DIR}/enterprise-attack.json" \
  "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json"

echo "[*] Download complete. STIX data located at: ${STIX_DIR}/enterprise-attack.json"
