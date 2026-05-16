from __future__ import annotations

ALLOWED_PRIORITIES = {
    "EMERGENCY",
    "ALERT",
    "CRITICAL",
    "ERROR",
    "WARNING",
    "NOTICE",
    "INFORMATIONAL",
    "DEBUG",
}
EXPECTED_RULE_NAMES = {
    "Unprivileged namespace or overlayfs exploit tooling",
    "Suspicious read of kernel exploit-sensitive files",
    "Suspicious write of kernel exploit-sensitive files",
}
EXPECTED_MACRO_NAMES = {
    "user_read_sensitive_file_conditions",
    "kev_namespace_or_overlay_activity",
}
EXPECTED_LIST_NAMES = {
    "known_ptrace_binaries",
    "kev_kernel_sensitive_read_paths",
    "kev_kernel_sensitive_write_paths",
}


def _entries_with_key(entries: list[dict], key: str) -> list[dict]:
    return [entry for entry in entries if key in entry]


def _names_for(entries: list[dict], key: str) -> list[str]:
    return [entry[key] for entry in _entries_with_key(entries, key)]


def test_falco_rules_load_as_non_empty_sequence(falco_rules: list[dict]) -> None:
    assert isinstance(falco_rules, list)
    assert falco_rules


def test_falco_rules_keep_unique_names_per_entry_type(falco_rules: list[dict]) -> None:
    for key in ("list", "macro", "rule"):
        names = _names_for(falco_rules, key)
        assert len(names) == len(set(names)), f"duplicate Falco {key} names: {names}"


def test_expected_local_rule_building_blocks_exist(falco_rules: list[dict]) -> None:
    assert EXPECTED_LIST_NAMES.issubset(set(_names_for(falco_rules, "list")))
    assert EXPECTED_MACRO_NAMES.issubset(set(_names_for(falco_rules, "macro")))
    assert EXPECTED_RULE_NAMES.issubset(set(_names_for(falco_rules, "rule")))


def test_custom_rules_have_required_fields(falco_rules: list[dict]) -> None:
    for entry in _entries_with_key(falco_rules, "rule"):
        assert entry["rule"].strip()
        assert entry["desc"].strip()
        assert entry["condition"].strip()
        assert entry["output"].strip()
        assert entry["priority"].upper() in ALLOWED_PRIORITIES
        assert isinstance(entry["tags"], list)
        assert entry["tags"]


def test_expected_kev_rules_keep_kev_and_mitre_tags(falco_rules: list[dict]) -> None:
    rules_by_name = {
        entry["rule"]: entry for entry in _entries_with_key(falco_rules, "rule")
    }

    for rule_name in EXPECTED_RULE_NAMES:
        entry = rules_by_name[rule_name]
        assert "kev" in entry["tags"]
        assert any(tag.startswith("T") for tag in entry["tags"])


def test_custom_lists_have_non_empty_unique_items(falco_rules: list[dict]) -> None:
    for entry in _entries_with_key(falco_rules, "list"):
        items = entry.get("items", [])
        assert items
        assert len(items) == len(set(items)), (
            f"duplicate items in Falco list {entry['list']}"
        )


def test_rule_outputs_include_field_placeholders(falco_rules: list[dict]) -> None:
    for entry in _entries_with_key(falco_rules, "rule"):
        output = entry["output"]
        assert "%" in output
        assert any(token in output for token in ("%proc.", "%user.", "%fd."))
