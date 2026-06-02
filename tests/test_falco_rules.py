"""Tests for falco_rules.local.yaml"""
import os
import yaml

RULES_FILE = os.path.join(os.path.dirname(__file__), "..", "falco_rules.local.yaml")


def load_rules():
    with open(RULES_FILE) as f:
        docs = list(yaml.safe_load_all(f))
    rules = {}
    for doc in docs:
        if isinstance(doc, list):
            for item in doc:
                if isinstance(item, dict) and "rule" in item and "tags" in item:
                    rules[item["rule"]] = item
        elif isinstance(doc, dict) and "rule" in doc and "tags" in doc:
            rules[doc["rule"]] = doc
    return rules


def test_unexpected_outbound_rule_exists():
    rules = load_rules()
    assert "Unexpected Outbound Network Connection" in rules, \
        "Rule 'Unexpected Outbound Network Connection' not found in falco_rules.local.yaml"


def test_unexpected_outbound_rule_has_c2_tags():
    rules = load_rules()
    rule = rules["Unexpected Outbound Network Connection"]
    tags = rule.get("tags", [])
    assert "mitre_command_and_control" in tags, \
        f"Tag 'mitre_command_and_control' missing from rule tags: {tags}"
    assert "T1071" in tags, \
        f"Tag 'T1071' missing from rule tags: {tags}"


def test_sub_techniques_no_bare_T1059():
    """Execution from Temporary Directory should not use bare T1059."""
    rules = load_rules()
    rule = rules.get("Execution from Temporary Directory", {})
    tags = rule.get("tags", [])
    assert "T1059" not in tags, \
        "Bare T1059 found; should use a sub-technique like T1059.004"


def test_sub_techniques_no_bare_T1003():
    """Credential Dumping Tool Execution should not use bare T1003."""
    rules = load_rules()
    rule = rules.get("Credential Dumping Tool Execution", {})
    tags = rule.get("tags", [])
    assert "T1003" not in tags, \
        "Bare T1003 found; should use a sub-technique like T1003.007 or T1003.008"
