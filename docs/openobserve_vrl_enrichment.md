# OpenObserve VRL MITRE ATT&CK Log Enrichment Guide

This guide details how to implement real-time log enrichment within **OpenObserve** using the generated `mitre_lookup.csv` catalog and **VRL (Vector Remap Language)** pipelines.

By integrating this pipeline, incoming threat-detection alerts from both **Falco (eBPF)** and **OSquery (FIM/SQL)** will be dynamically decorated with canonical MITRE ATT&CK names, descriptions, associated tactics, and official references.

---

## 1. Uploading the Lookup Table to OpenObserve

OpenObserve supports flat CSV databases as reference lookup tables (enrichment lists). You can import `alerts/openobserve/mitre_lookup.csv` through either the web console or programmatically using the OpenObserve REST API.

### Option A: REST API Ingestion (Recommended)
Execute the following curl command to programmatically provision or overwrite the `mitre_lookup` database in your local/production cluster:

```bash
curl -X POST "http://localhost:5080/api/default/dictionary/mitre_lookup" \
  -H "Authorization: Basic $(echo -n "${OPENOBSERVE_USERNAME}:${OPENOBSERVE_PASSWORD}" | base64)" \
  -H "Content-Type: text/csv" \
  --data-binary "@alerts/openobserve/mitre_lookup.csv"
```

### Option B: OpenObserve Console Interface
1. Login to your **OpenObserve Console** (e.g. `http://localhost:5080`).
2. Navigate to **Settings** ➔ **Dictionaries** (or **Enrichment Tables**).
3. Click **Add New Table** / **Upload Dictionary**.
4. Name the dictionary exactly `mitre_lookup`.
5. Upload `alerts/openobserve/mitre_lookup.csv` and click **Save**.

---

## 2. Setting Up the Vector Remap Language (VRL) Pipelines

To perform real-time joins, we attach a VRL processor to the log streams. In OpenObserve, navigate to **Pipelines** ➔ **VRL Functions** and create a pipeline associated with the `falco` and `osquery` streams.

### VRL Script: `enrich_mitre_attack`
Add the following VRL script to the ingest processor flow:

```vrl
# 1. Initialize or resolve the MITRE Technique ID from the incoming log record
mitre_id = ""

# Check for Falco MITRE tags or fields
if exists(.rule) && is_string(.rule) {
    # Extract ID from Falco rules that include a MITRE ID tag
    # Example: "Clear Command History (Truncate) [T1070.003]"
    matches = regex_match!(.rule, r'\[(?P<id>T\d{4}(?:\.\d{3})?)\]')
    if is_map(matches) && exists(matches.id) {
        mitre_id = matches.id
    }
}

# Fallback: check explicit mitre_id or tags field
if mitre_id == "" {
    mitre_id = .mitre_id || .output_fields["mitre_id"] || ""
}

# 2. Perform dynamic lookup join against the mitre_lookup dictionary
if mitre_id != "" {
    # lookup(dictionary_name, key) returns a map/JSON object of the matching row
    mitre_record = lookup("mitre_lookup", mitre_id)
    
    if is_map(mitre_record) {
        # Initialize and populate the mitre metadata block
        .mitre = {}
        .mitre.id = mitre_id
        .mitre.technique_name = mitre_record.name
        .mitre.tactic = mitre_record.tactic
        .mitre.description = mitre_record.description
        .mitre.url = mitre_record.url
        
        # Log metadata decoration tracking
        .enriched = true
        .enriched_by = "mitre_stix_pipeline"
    }
}
```

---

## 3. Threat-Telemetry Payload Transformation Demo

### Before Enrichment (Raw Ingest Payload)
When Falco intercepts a destructive disk-wiping signature, the telemetry pipeline forwards the following raw log:

```json
{
  "_timestamp": "2026-06-01T20:00:00Z",
  "rule": "Secure Erase or Destructive Disk Wiping [T1485]",
  "priority": "Critical",
  "output": "Secure Erase or Destructive Disk Wiping detected on /dev/sdb by dd (user=root)",
  "output_fields": {
    "proc.name": "dd",
    "user.name": "root"
  }
}
```

### After Enrichment (Decorated Pipeline Output)
Once processed by the VRL pipeline, the log entry is automatically enriched with structured security metadata:

```json
{
  "_timestamp": "2026-06-01T20:00:00Z",
  "rule": "Secure Erase or Destructive Disk Wiping [T1485]",
  "priority": "Critical",
  "output": "Secure Erase or Destructive Disk Wiping detected on /dev/sdb by dd (user=root)",
  "output_fields": {
    "proc.name": "dd",
    "user.name": "root"
  },
  "mitre": {
    "id": "T1485",
    "technique_name": "Data Destruction",
    "tactic": "Impact",
    "description": "Adversaries may wipe or corrupt raw disk data on specific systems or in large numbers in a network to interrupt availability to system and network resources. With direct write access to a disk, adversaries may...",
    "url": "https://attack.mitre.org/techniques/T1485"
  },
  "enriched": true,
  "enriched_by": "mitre_stix_pipeline"
}
```

---

## 4. Verification and Pipeline Integration Testing

To verify the parser's output integrity and ensure that all rules match canonical tags:

1. Confirm the CSV file exists and has size:
   ```bash
   ls -la alerts/openobserve/mitre_lookup.csv
   ```
2. Verify Rule Alignment:
   Run the static validator task to verify that active configurations are fully aligned:
   ```bash
   task test-detection-coverage
   ```
3. Real-Time Dynamic Test (Optional):
   Use the `caldera_otel_harness.py` to trigger a safe ability like `lnx_destructive_shred_erase.yml` (MITRE ID `T1485`) and inspect the trace logs in the OpenObserve dashboard to confirm metadata decoration is active.
