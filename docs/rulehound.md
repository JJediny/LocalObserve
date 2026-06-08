# Rulehound Detection Rule Import

## What is Rulehound?

[Rulehound](https://github.com/infosecB/Rulehound) is a catalog and search engine for publicly available, open-source threat detection rulesets. It indexes rules across multiple detection engines including **Sigma**, **Splunk Security Content**, **Elastic Detection Rules**, **Panther Rules**, and **Anvilogic Forge Rules**.

Rulehound provides a centralized way to discover and reference community detection content mapped to MITRE ATT&CK techniques, making it easier to build comprehensive detection coverage.

## How the Import Works

The `scripts/import_rulehound_rules.py` script bridges Rulehound's indexed rulesets and LocalObserve's Falco-based detection pipeline:

```
[Sigma Rules (SigmaHQ — indexed by Rulehound)]
         │
         ▼
[scripts/import_rulehound_rules.py] ── Translates & converts
         │
         ├─► [rules/rulehound/*.yaml]        ← Individual Falco rules
         └─► [rules/rulehound/rulehound_falco_rules.yaml]  ← Combined rules file
```

### Conversion Logic

The script fetches Sigma YAML rules from the SigmaHQ repository (the primary source indexed by Rulehound) and converts them into Falco-compatible YAML:

| Sigma Category | Falco Event Mapping |
|---|---|
| `process_creation` | `spawned_process` |
| `file_event` | `open_write` |
| `network_connection` | `outbound` |
| `auditd` | `spawned_process` |
| `builtin` | `spawned_process` |

MITRE ATT&CK tags are automatically translated:
- `attack.defense_evasion` → `mitre_defense_evasion`
- `attack.t1070.002` → `T1070.002`

Sigma severity levels map to Falco priorities:
- `critical` / `high` → `CRITICAL`
- `medium` → `WARNING`
- `low` / `informational` → `INFO`

## Usage

### Basic Import

```bash
# Fetch process_creation and file_event rules (default categories)
python scripts/import_rulehound_rules.py

# Specify output directory and categories
python scripts/import_rulehound_rules.py --output rules/rulehound/ --categories process_creation,file_event,network_connection

# Use a GitHub token to avoid rate limits
GITHUB_TOKEN=ghp_xxxx python scripts/import_rulehound_rules.py
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--output`, `-o` | `rules/rulehound/` | Output directory for converted Falco rules |
| `--categories`, `-c` | `process_creation,file_event` | Comma-separated Sigma rule categories to fetch |

### Available Categories

- `process_creation` — Process execution/spawning rules
- `file_event` — File modification/creation rules
- `network_connection` — Network activity rules
- `auditd` — Linux auditd-based rules
- `builtin` — Built-in detection rules

## Output Structure

After running the script, the `rules/rulehound/` directory will contain:

```
rules/rulehound/
├── rulehound_falco_rules.yaml    ← Combined file with all converted rules
├── linux_clear_log_attempts.yaml
├── linux_shred_file_deletion.yaml
├── linux_ssh_authorized_keys_modification.yaml
└── ...                           ← One file per converted rule
```

## Integrating with LocalObserve

To add the imported rules to your Falco configuration:

1. Run the import script to generate the rules
2. Append the combined rules file to your Falco local rules:
   ```bash
   cat rules/rulehound/rulehound_falco_rules.yaml >> falco_rules.local.yaml
   ```
3. Restart Falco to pick up the new rules

## Alignment Validation

The existing `scripts/import_rulehound_mappings.py` script validates that Rulehound-mapped rules in `docs/rulehound_mappings.md` are active in `falco_rules.local.yaml` and `osqueryd.conf`. The new import script complements this by pulling new rules directly from upstream sources.

## Testing

```bash
# Unit tests for the conversion logic
pytest tests/test_rulehound_import.py -v

# Integration test with live GitHub API (requires network)
python scripts/import_rulehound_rules.py --categories process_creation
```

## References

- [Rulehound](https://github.com/infosecB/Rulehound) — Detection rules catalog
- [SigmaHQ/sigma](https://github.com/SigmaHQ/sigma) — Sigma rule repository
- [Rulehound Mappings](../docs/rulehound_mappings.md) — LocalObserve's existing alignment matrix
- [Falco Rules](https://falco.org/docs/rules/) — Falco rule documentation
