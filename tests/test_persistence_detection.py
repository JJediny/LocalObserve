"""Tests for rules/persistence_techniques.yaml

Validates that the persistence detection Falco rules file:
  1. Loads as valid YAML
  2. Contains expected rule definitions for each persistence category
  3. Each rule has the required Falco rule fields (desc, condition, output, priority, tags)
  4. MITRE ATT&CK technique tags are present and correctly formatted
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PERSISTENCE_RULES_PATH = REPO_ROOT / "rules" / "persistence_techniques.yaml"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def persistence_rules():
    """Load and return the persistence techniques rules YAML."""
    raw = PERSISTENCE_RULES_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    assert data is not None, "persistence_techniques.yaml loaded as None"
    return data


@pytest.fixture(scope="module")
def parsed_rules(persistence_rules):
    """Return a dict mapping rule name -> rule definition for rule-type items."""
    items = persistence_rules if isinstance(persistence_rules, list) else [persistence_rules]
    rules = {}
    for item in items:
        if isinstance(item, dict) and "rule" in item:
            rules[item["rule"]] = item
    return rules


@pytest.fixture(scope="module")
def parsed_macros(persistence_rules):
    """Return a dict mapping macro name -> macro definition for macro-type items."""
    items = persistence_rules if isinstance(persistence_rules, list) else [persistence_rules]
    macros = {}
    for item in items:
        if isinstance(item, dict) and "macro" in item:
            macros[item["macro"]] = item
    return macros


@pytest.fixture(scope="module")
def parsed_lists(persistence_rules):
    """Return a dict mapping list name -> list definition for list-type items."""
    items = persistence_rules if isinstance(persistence_rules, list) else [persistence_rules]
    lists = {}
    for item in items:
        if isinstance(item, dict) and "list" in item:
            lists[item["list"]] = item
    return lists


# ---------------------------------------------------------------------------
# Required rules by persistence category (issue #37)
# ---------------------------------------------------------------------------

REQUIRED_RULES = {
    "cron_at": {
        "rule_names": [
            "Cron Directory or Spool File Write by Non-Admin",
            "At Job Scheduling Command Execution",
            "Crontab Execution by Non-Standard Parent",
        ],
        "min_match": 1,
        "technique_tags": ["T1053.003", "T1053.005"],
    },
    "ssh_authorized_keys": {
        "rule_names": [
            "SSH Authorized_keys File Write",
            "SSH Authorized_keys2 File Write",
            "SSH Config Modification for Persistence",
        ],
        "min_match": 1,
        "technique_tags": ["T1098.004"],
    },
    "systemd": {
        "rule_names": [
            "Systemd Service Unit File Creation",
            "Systemd Timer Unit Creation",
            "Systemd User Service Creation",
            "Systemctl Enable or Start by Non-Admin",
        ],
        "min_match": 1,
        "technique_tags": ["T1543.002"],
    },
    "bash_profile_rc": {
        "rule_names": [
            "Shell Profile or RC File Modification",
            "System-wide Shell Profile Modification",
        ],
        "min_match": 1,
        "technique_tags": ["T1546.004"],
    },
    "ld_preload_library_path": {
        "rule_names": [
            "LD_LIBRARY_PATH Hijack Attempt",
            "LD_PRELOAD Execution from Non-Standard Path",
            "etc ld.so.preload File Write",
        ],
        "min_match": 1,
        "technique_tags": ["T1574.006"],
    },
    "setuid_setgid": {
        "rule_names": [
            "Setuid Binary Creation via chmod",
            "Setgid Binary Creation via chmod",
            "Setuid Setgid Binary Creation via install",
        ],
        "min_match": 1,
        "technique_tags": ["T1548.001"],
    },
}

REQUIRED_RULE_NAME_SET = set()
for _cat in REQUIRED_RULES.values():
    REQUIRED_RULE_NAME_SET.update(_cat["rule_names"])

VALID_PRIORITIES = {
    "EMERGENCY", "ALERT", "CRITICAL", "ERROR",
    "WARNING", "NOTICE", "INFORMATIONAL", "DEBUG",
}

# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------


class TestPersistenceRulesFile:
    """Validate the persistence techniques YAML file structure."""

    def test_file_exists(self):
        assert PERSISTENCE_RULES_PATH.is_file(), (
            f"persistence_techniques.yaml not found at {PERSISTENCE_RULES_PATH}"
        )

    def test_yaml_loads_as_list(self, persistence_rules):
        assert isinstance(persistence_rules, list), (
            "Expected YAML to load as a list of items"
        )

    def test_contains_required_rule_count(self, parsed_rules):
        found = set(parsed_rules.keys())
        missing = REQUIRED_RULE_NAME_SET - found
        assert len(missing) == 0, (
            f"Missing required rules: {missing}. "
            f"Found: {sorted(found)}"
        )

    def test_all_required_categories_covered(self, parsed_rules):
        """Every persistence category from issue #37 must have at least one rule."""
        for category, spec in REQUIRED_RULES.items():
            found = any(name in parsed_rules for name in spec["rule_names"])
            assert found, (
                f"Category '{category}' has no matching rules. "
                f"Expected at least one of: {spec['rule_names']}"
            )


class TestPersistenceRuleStructure:
    """Validate that every rule has the required Falco fields."""

    @pytest.mark.parametrize("rule_name", REQUIRED_RULE_NAME_SET)
    def test_rule_has_description(self, parsed_rules, rule_name):
        assert rule_name in parsed_rules, f"Rule '{rule_name}' not found"
        rule = parsed_rules[rule_name]
        assert "desc" in rule, f"Rule '{rule_name}' missing 'desc' field"

    @pytest.mark.parametrize("rule_name", REQUIRED_RULE_NAME_SET)
    def test_rule_has_condition(self, parsed_rules, rule_name):
        assert rule_name in parsed_rules
        rule = parsed_rules[rule_name]
        assert "condition" in rule, f"Rule '{rule_name}' missing 'condition' field"

    @pytest.mark.parametrize("rule_name", REQUIRED_RULE_NAME_SET)
    def test_rule_has_output(self, parsed_rules, rule_name):
        assert rule_name in parsed_rules
        rule = parsed_rules[rule_name]
        assert "output" in rule, f"Rule '{rule_name}' missing 'output' field"

    @pytest.mark.parametrize("rule_name", REQUIRED_RULE_NAME_SET)
    def test_rule_has_priority(self, parsed_rules, rule_name):
        assert rule_name in parsed_rules
        rule = parsed_rules[rule_name]
        assert "priority" in rule, f"Rule '{rule_name}' missing 'priority' field"
        assert rule["priority"] in VALID_PRIORITIES, (
            f"Rule '{rule_name}' has invalid priority: {rule['priority']}"
        )

    @pytest.mark.parametrize("rule_name", REQUIRED_RULE_NAME_SET)
    def test_rule_has_tags(self, parsed_rules, rule_name):
        assert rule_name in parsed_rules
        rule = parsed_rules[rule_name]
        assert "tags" in rule, f"Rule '{rule_name}' missing 'tags' field"
        assert isinstance(rule["tags"], list), f"Rule '{rule_name}' tags must be a list"
        assert len(rule["tags"]) > 0, f"Rule '{rule_name}' has empty tags list"


class TestPersistenceMitreTags:
    """Ensure required MITRE ATT&CK technique IDs are present."""

    @pytest.mark.parametrize("category", list(REQUIRED_RULES.keys()))
    def test_category_has_mitre_technique_tags(self, parsed_rules, category):
        spec = REQUIRED_RULES[category]
        matching = [
            parsed_rules[name]
            for name in spec["rule_names"]
            if name in parsed_rules
        ]
        assert len(matching) > 0, f"No matching rules for category '{category}'"

        for rule in matching:
            tags = rule.get("tags", [])
            has_mitre_persistence = "mitre_persistence" in tags or "mitre_privilege_escalation" in tags
            # At least one MITRE technique tag should be present
            has_technique = any(t.startswith("T1") for t in tags)
            assert has_technique, (
                f"Rule '{rule['rule']}' has no MITRE technique tags: {tags}"
            )

    def test_cron_rules_have_correct_technique(self, parsed_rules):
        for name in REQUIRED_RULES["cron_at"]["rule_names"]:
            if name in parsed_rules:
                tags = parsed_rules[name]["tags"]
                assert any(t in tags for t in ["T1053.003", "T1053.005"]), (
                    f"Rule '{name}' missing expected cron technique tags"
                )

    def test_ssh_rules_have_correct_technique(self, parsed_rules):
        for name in REQUIRED_RULES["ssh_authorized_keys"]["rule_names"]:
            if name in parsed_rules:
                tags = parsed_rules[name]["tags"]
                assert "T1098.004" in tags, (
                    f"Rule '{name}' missing T1098.004 tag"
                )

    def test_systemd_rules_have_correct_technique(self, parsed_rules):
        for name in REQUIRED_RULES["systemd"]["rule_names"]:
            if name in parsed_rules:
                tags = parsed_rules[name]["tags"]
                assert "T1543.002" in tags, (
                    f"Rule '{name}' missing T1543.002 tag"
                )

    def test_bash_profile_rules_have_correct_technique(self, parsed_rules):
        for name in REQUIRED_RULES["bash_profile_rc"]["rule_names"]:
            if name in parsed_rules:
                tags = parsed_rules[name]["tags"]
                assert "T1546.004" in tags or "T1546.005" in tags, (
                    f"Rule '{name}' missing T1546.004/T1546.005 tag"
                )

    def test_ld_preload_rules_have_correct_technique(self, parsed_rules):
        for name in REQUIRED_RULES["ld_preload_library_path"]["rule_names"]:
            if name in parsed_rules:
                tags = parsed_rules[name]["tags"]
                assert "T1574.006" in tags, (
                    f"Rule '{name}' missing T1574.006 tag"
                )

    def test_setuid_rules_have_correct_technique(self, parsed_rules):
        for name in REQUIRED_RULES["setuid_setgid"]["rule_names"]:
            if name in parsed_rules:
                tags = parsed_rules[name]["tags"]
                assert "T1548.001" in tags, (
                    f"Rule '{name}' missing T1548.001 tag"
                )


class TestPersistenceLists:
    """Validate supporting list definitions."""

    def test_cron_directories_list_exists(self, parsed_lists):
        assert "cron_directories" in parsed_lists, "Missing 'cron_directories' list"

    def test_cron_admin_binaries_list_exists(self, parsed_lists):
        assert "cron_admin_binaries" in parsed_lists, "Missing 'cron_admin_binaries' list"

    def test_ssh_admin_binaries_list_exists(self, parsed_lists):
        assert "ssh_admin_binaries" in parsed_lists, "Missing 'ssh_admin_binaries' list"

    def test_systemd_service_directories_list_exists(self, parsed_lists):
        assert "systemd_service_directories" in parsed_lists, "Missing 'systemd_service_directories' list"

    def test_systemd_admin_binaries_list_exists(self, parsed_lists):
        assert "systemd_admin_binaries" in parsed_lists, "Missing 'systemd_admin_binaries' list"

    def test_shell_profile_files_list_exists(self, parsed_lists):
        assert "shell_profile_files" in parsed_lists, "Missing 'shell_profile_files' list"

    def test_shell_profile_writers_list_exists(self, parsed_lists):
        assert "shell_profile_writers" in parsed_lists, "Missing 'shell_profile_writers' list"


class TestNoDuplicateRuleNames:
    """Ensure no duplicate rule names in the persistence rules file."""

    def test_no_duplicate_rules(self, persistence_rules):
        items = persistence_rules if isinstance(persistence_rules, list) else [persistence_rules]
        names = [item["rule"] for item in items if isinstance(item, dict) and "rule" in item]
        assert len(names) == len(set(names)), f"Duplicate rule names found: {[n for n in names if names.count(n) > 1]}"
