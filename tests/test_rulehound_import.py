"""Tests for scripts/import_rulehound_rules.py

Validates the import script runs without errors and produces valid output,
including unit tests for the Sigma-to-Falco conversion logic.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "import_rulehound_rules.py"
RULES_DIR = REPO_ROOT / "rules" / "rulehound"

# ---------------------------------------------------------------------------
# Ensure the script is importable
# ---------------------------------------------------------------------------

sys.path.insert(0, str(SCRIPT_PATH.parent))
import_rulehound_rules = importlib.import_module("import_rulehound_rules")


# ===========================================================================
# Unit tests – flattening helper
# ===========================================================================


class TestFlattenDetection:
    """Test _flatten_detection correctly merges selection groups."""

    def test_nested_selection(self):
        detection = {
            "selection": {
                "Image|endswith": ["/rm", "/shred"],
                "CommandLine|contains": "/var/log",
            },
            "condition": "selection",
        }
        flat = import_rulehound_rules._flatten_detection(detection)
        assert "Image|endswith" in flat
        assert "/rm" in flat["Image|endswith"]
        assert "/shred" in flat["Image|endswith"]
        # condition should be excluded
        assert "condition" not in flat

    def test_top_level_list(self):
        detection = {
            "Image|endswith": ["/bin/bash"],
        }
        flat = import_rulehound_rules._flatten_detection(detection)
        assert "/bin/bash" in flat.get("Image|endswith", [])

    def test_empty(self):
        assert import_rulehound_rules._flatten_detection({}) == {}

    def test_multiple_groups_merged(self):
        detection = {
            "selection": {"Image|endswith": ["/rm"]},
            "filter": {"Image|endswith": ["/shred"]},
            "condition": "selection and not filter",
        }
        flat = import_rulehound_rules._flatten_detection(detection)
        assert "/rm" in flat["Image|endswith"]
        assert "/shred" in flat["Image|endswith"]


# ===========================================================================
# Unit tests – conversion helpers
# ===========================================================================


class TestMitreTags:
    """Test _mitre_tags conversion."""

    def test_tactic_mapping(self):
        tags = import_rulehound_rules._mitre_tags(["attack.defense_evasion"])
        assert "mitre_defense_evasion" in tags

    def test_technique_id(self):
        tags = import_rulehound_rules._mitre_tags(["attack.t1070.002"])
        assert "T1070.002" in tags

    def test_bare_technique_id(self):
        tags = import_rulehound_rules._mitre_tags(["attack.t1059"])
        assert "T1059" in tags

    def test_deduplication(self):
        tags = import_rulehound_rules._mitre_tags(
            ["attack.defense_evasion", "attack.defense_evasion"]
        )
        assert tags.count("mitre_defense_evasion") == 1

    def test_empty_input(self):
        assert import_rulehound_rules._mitre_tags([]) == []


class TestCategoryToFalcoEvent:
    """Test _category_to_falco_event mapping."""

    def test_process_creation(self):
        assert import_rulehound_rules._category_to_falco_event("process_creation") == "spawned_process"

    def test_file_event(self):
        assert import_rulehound_rules._category_to_falco_event("file_event") == "open_write"

    def test_network_connection(self):
        assert import_rulehound_rules._category_to_falco_event("network_connection") == "outbound"

    def test_unknown_defaults(self):
        assert import_rulehound_rules._category_to_falco_event("unknown_cat") == "spawned_process"


class TestExtractProcs:
    """Test _extract_procs helper."""

    def test_single_image(self):
        detection = {"selection": {"Image": "/usr/bin/shred"}, "condition": "selection"}
        procs = import_rulehound_rules._extract_procs(detection)
        assert "shred" in procs

    def test_endswith_nested(self):
        detection = {
            "selection": {"Image|endswith": ["/rm", "/shred", "/unlink"]},
            "condition": "selection",
        }
        procs = import_rulehound_rules._extract_procs(detection)
        assert "rm" in procs
        assert "shred" in procs

    def test_wildcard_filtered(self):
        detection = {
            "selection": {"Image|endswith": ["/clear", "/bash*"]},
            "condition": "selection",
        }
        procs = import_rulehound_rules._extract_procs(detection)
        # Wildcard entries should be filtered out
        assert all("*" not in p for p in procs)

    def test_empty(self):
        assert import_rulehound_rules._extract_procs({}) == []

    def test_top_level_image(self):
        detection = {"Image": "/usr/bin/whoami"}
        procs = import_rulehound_rules._extract_procs(detection)
        assert "whoami" in procs


class TestExtractPaths:
    """Test _extract_paths helper."""

    def test_target_filename_nested(self):
        detection = {
            "selection": {"TargetFilename|endswith": "/.ssh/authorized_keys"},
            "condition": "selection",
        }
        paths = import_rulehound_rules._extract_paths(detection)
        assert "/.ssh/authorized_keys" in paths

    def test_path_contains_list(self):
        detection = {
            "selection": {"TargetFilename|contains": ["/var/log", "/etc/shadow"]},
            "condition": "selection",
        }
        paths = import_rulehound_rules._extract_paths(detection)
        assert "/var/log" in paths

    def test_empty(self):
        assert import_rulehound_rules._extract_paths({}) == []


# ===========================================================================
# Integration tests – sigma_to_falco_rule
# ===========================================================================


class TestSigmaToFalcoRule:
    """Test the full Sigma->Falco conversion."""

    def test_basic_process_creation_rule(self):
        sigma = {
            "title": "Test Clear Logs",
            "description": "Detects log clearing",
            "level": "medium",
            "tags": ["attack.defense_evasion", "attack.t1070.002"],
            "logsource": {"product": "linux", "category": "process_creation"},
            "detection": {
                "selection": {
                    "Image|endswith": ["/rm", "/shred"],
                    "CommandLine|contains": "/var/log",
                },
                "condition": "selection",
            },
        }
        result = import_rulehound_rules.sigma_to_falco_rule(sigma)
        assert result is not None
        assert result["rule"] == "Test Clear Logs"
        assert "spawned_process" in result["condition"]
        assert "rm" in result["condition"]
        assert "shred" in result["condition"]
        assert result["priority"] == "WARNING"
        assert "mitre_defense_evasion" in result["tags"]
        assert "T1070.002" in result["tags"]
        assert "rulehound" in result["tags"]

    def test_file_event_rule(self):
        sigma = {
            "title": "SSH Authorized Keys Modification",
            "description": "Detects writes to authorized_keys",
            "level": "high",
            "tags": ["attack.persistence", "attack.t1098.004"],
            "logsource": {"product": "linux", "category": "file_event"},
            "detection": {
                "selection": {
                    "TargetFilename|endswith": "/.ssh/authorized_keys",
                },
                "condition": "selection",
            },
        }
        result = import_rulehound_rules.sigma_to_falco_rule(sigma)
        assert result is not None
        assert "open_write" in result["condition"]
        assert result["priority"] == "CRITICAL"
        assert "mitre_persistence" in result["tags"]

    def test_rule_with_no_detections_skipped(self):
        sigma = {
            "title": "Empty Rule",
            "description": "No detection fields",
            "level": "low",
            "logsource": {"category": "process_creation"},
            "detection": {"condition": "selection"},
        }
        result = import_rulehound_rules.sigma_to_falco_rule(sigma)
        # Should return None since no procs/paths can be extracted
        assert result is None

    def test_rulehound_tag_always_present(self):
        sigma = {
            "title": "Minimal Rule",
            "description": "Minimal",
            "level": "medium",
            "logsource": {"category": "process_creation"},
            "detection": {
                "selection": {"Image": "/usr/bin/whoami"},
                "condition": "selection",
            },
        }
        result = import_rulehound_rules.sigma_to_falco_rule(sigma)
        assert result is not None
        assert "rulehound" in result["tags"]

    def test_description_truncation(self):
        very_long = "A" * 500
        sigma = {
            "title": "Long Desc Rule",
            "description": very_long,
            "level": "medium",
            "logsource": {"category": "process_creation"},
            "detection": {"selection": {"Image": "/bin/ls"}, "condition": "selection"},
        }
        result = import_rulehound_rules.sigma_to_falco_rule(sigma)
        assert result is not None
        assert len(result["desc"]) <= 300

    def test_network_connection_category(self):
        sigma = {
            "title": "Suspicious Outbound Connection",
            "description": "Test",
            "level": "high",
            "logsource": {"category": "network_connection"},
            "detection": {"selection": {"Image": "/usr/bin/nc"}, "condition": "selection"},
        }
        result = import_rulehound_rules.sigma_to_falco_rule(sigma)
        assert result is not None
        assert "outbound" in result["condition"]

    def test_linux_tag_always_present(self):
        sigma = {
            "title": "Linux Test",
            "description": "Test",
            "level": "medium",
            "logsource": {"category": "process_creation"},
            "detection": {"selection": {"Image": "/bin/test"}, "condition": "selection"},
        }
        result = import_rulehound_rules.sigma_to_falco_rule(sigma)
        assert result is not None
        assert "linux" in result["tags"]


# ===========================================================================
# End-to-end tests – output validity
# ===========================================================================


class TestOutputValidity:
    """Test that the output directory structure is valid when rules exist."""

    def test_output_dir_structure(self):
        """If the rules/rulehound/ directory exists, validate structure."""
        if not RULES_DIR.exists():
            pytest.skip("No rulehound output directory yet (run import first)")

        combined = RULES_DIR / "rulehound_falco_rules.yaml"
        if combined.exists():
            with open(combined, "r") as fh:
                rules = yaml.safe_load(fh)
            assert isinstance(rules, list), "Combined file should contain a list"
            for rule in rules:
                assert isinstance(rule, dict), "Each rule must be a dict"
                assert "rule" in rule, "Each rule must have a 'rule' key"
                assert "condition" in rule, "Each rule must have a 'condition' key"
                assert "priority" in rule, "Each rule must have a 'priority' key"

    def test_individual_rule_files_valid_yaml(self):
        """Each individual rule YAML file should be valid."""
        if not RULES_DIR.exists():
            pytest.skip("No rulehound output directory yet (run import first)")

        yml_files = list(RULES_DIR.glob("*.yaml")) + list(RULES_DIR.glob("*.yml"))
        # Skip the combined file
        yml_files = [f for f in yml_files if f.name != "rulehound_falco_rules.yaml"]

        for yml_file in yml_files[:5]:  # Spot-check up to 5 files
            with open(yml_file, "r") as fh:
                content = yaml.safe_load(fh)
            assert isinstance(content, list), f"{yml_file.name} should contain a list"


class TestScriptModule:
    """Verify the module loaded correctly."""

    def test_module_imports(self):
        assert hasattr(import_rulehound_rules, "fetch_sigma_rules")
        assert hasattr(import_rulehound_rules, "convert_and_write")
        assert hasattr(import_rulehound_rules, "sigma_to_falco_rule")
        assert hasattr(import_rulehound_rules, "_flatten_detection")

    def test_default_output_dir_exists(self):
        assert hasattr(import_rulehound_rules, "DEFAULT_OUTPUT_DIR")

    def test_priority_map_complete(self):
        pm = import_rulehound_rules.PRIORITY_MAP
        assert "critical" in pm
        assert "high" in pm
        assert "medium" in pm
        assert "low" in pm
