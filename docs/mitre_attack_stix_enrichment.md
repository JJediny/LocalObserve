# MITRE ATT&CK STIX Data Source Enrichment & Coverage Mapping

The [MITRE Cyber Threat Intelligence (CTI) repository](https://github.com/mitre/cti) provides the ATT&CK framework formatted as STIX 2.1 JSON. While we aren't establishing a direct integration pipeline yet, this document outlines how this repository serves as a foundational dataset for repeatable log enrichment and for approximating rule/controls coverage across our telemetry pipeline (Falco, OSquery, ClamAV, OpenObserve).

## 1. Understanding the STIX 2.1 Data Structure

The `enterprise-attack.json` file contains several key STIX Domain Objects (SDOs) crucial for mapping:

- **`attack-pattern`**: Represents the ATT&CK Techniques and Sub-techniques. 
  - *Key fields*: `name`, `description`, `kill_chain_phases` (Tactics), and `external_references` (contains the `external_id` like `T1059`).
- **`x-mitre-data-source` / `x-mitre-data-component`**: Represents the system telemetry needed to detect a technique (e.g., `Process: Process Creation`, `File: File Modification`).
- **`course-of-action`**: Represents mitigations.
- **`relationship`**: Connects techniques to data sources, mitigations, and threat actors.

## 2. Event Enrichment Strategy

By leveraging the STIX JSON, we can transform raw alerts into context-rich incidents for SOC analysts in OpenObserve.

### The Repeatable Process
1. **Rule Tagging**: Ensure all security rules are tagged with their respective MITRE IDs.
   - *Falco*: Rules already include tags like `mitre_execution` or explicitly `T1059`.
   - *OSquery*: Queries in packs should be annotated with `mitre_id: T1078`.
   - *ClamAV/YARA*: Malware families detected by YARA (e.g., from Abuse.ch) can be mapped to techniques based on known threat intel reports.
2. **Lookup Tables**: A script parses `enterprise-attack.json` to generate a flat, optimized lookup table (e.g., `mitre_lookup.csv` mapping `T-ID -> Name, Tactic, Description, URL`).
3. **OpenObserve Enrichment**: 
   - Load the `mitre_lookup.csv` into OpenObserve as a reference list or enrichment table.
   - When an event with a `mitre_id` arrives, OpenObserve executes a VRL pipeline to join the event with the lookup table, appending fields like `mitre.tactic`, `mitre.technique_name`, and `mitre.description` directly to the log entry.

## 3. Approximating Rule and Controls Coverage

The MITRE STIX data acts as the "denominator" in our coverage equations. By mapping our capabilities against the STIX objects, we can quantify our defensive posture.

### Method A: Rule-to-Technique Mapping (Current Posture)
1. **Extract Enabled Rules**: Aggregate all active tags from Falco configs, OSquery packs, and YARA categorizations.
2. **Map to STIX Patterns**: Compare the extracted MITRE IDs against all `attack-pattern` objects in the STIX data.
3. **Calculate Metric**: `(Number of Unique Techniques Covered) / (Total MITRE Techniques)`.
4. **Outcome**: Generates a heatmap (often visualized in the MITRE ATT&CK Navigator using an exported JSON layer) showing which techniques have active detections and highlighting defensive gaps.

### Method B: Telemetry-to-Data Component Mapping (Theoretical Posture)
Instead of looking at rules, we look at the raw data we collect to understand what we *could* detect if we wrote the rules.
1. **Map Ingested Data**: 
   - *Falco system calls* -> Maps to `Process: Process Creation`, `Network Traffic: Network Connection`.
   - *OSquery `file_events`* -> Maps to `File: File Creation`, `File: File Modification`.
2. **Match with STIX Data Sources**: Query the STIX `relationship` objects to see which `attack-patterns` are linked to the `x-mitre-data-component`s we actively collect.
3. **Outcome**: Identifies techniques we have the telemetry to detect but lack the explicit rules for, driving rule-creation priorities.

## Summary

By maintaining a local sync of the MITRE CTI STIX repository, we establish a robust, standard nomenclature. This enables dynamic log enrichment in OpenObserve—turning a cryptic rule alert into an actionable narrative—and provides a mathematical framework for proving security coverage to stakeholders.
