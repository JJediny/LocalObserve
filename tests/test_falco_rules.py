"""Tests for falco_rules.local.yaml"""
import os
import yaml
import pytest


@pytest.fixture(scope="module")
def rules_dict(falco_rules) -> dict[str, dict]:
    rules = {}
    items = falco_rules if isinstance(falco_rules, list) else [falco_rules]
    for item in items:
        if isinstance(item, dict) and "rule" in item:
            rules[item["rule"]] = item
    return rules


def test_unexpected_outbound_rule_exists(rules_dict):
    assert "Unexpected Outbound Network Connection" in rules_dict, \
        "Rule 'Unexpected Outbound Network Connection' not found in falco_rules.local.yaml"


def test_unexpected_outbound_rule_has_c2_tags(rules_dict):
    assert "Unexpected Outbound Network Connection" in rules_dict
    rule = rules_dict["Unexpected Outbound Network Connection"]
    tags = rule.get("tags", [])
    assert "mitre_command_and_control" in tags, \
        f"Tag 'mitre_command_and_control' missing from rule tags: {tags}"
    assert "T1071" in tags, \
        f"Tag 'T1071' missing from rule tags: {tags}"


def test_sub_techniques_no_bare_T1059(rules_dict):
    """Execution from Temporary Directory should not use bare T1059."""
    assert "Execution from Temporary Directory" in rules_dict, \
        "Rule 'Execution from Temporary Directory' not found in falco_rules.local.yaml"
    rule = rules_dict["Execution from Temporary Directory"]
    tags = rule.get("tags", [])
    assert "T1059" not in tags, \
        "Bare T1059 found; should use a sub-technique like T1059.004"


def test_sub_techniques_no_bare_T1003(rules_dict):
    """Credential Dumping Tool Execution should not use bare T1003."""
    assert "Credential Dumping Tool Execution" in rules_dict, \
        "Rule 'Credential Dumping Tool Execution' not found in falco_rules.local.yaml"
    rule = rules_dict["Credential Dumping Tool Execution"]
    tags = rule.get("tags", [])
    assert "T1003" not in tags, \
        "Bare T1003 found; should use a sub-technique like T1003.007 or T1003.008"
