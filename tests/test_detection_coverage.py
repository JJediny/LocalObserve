from __future__ import annotations

"""
test_detection_coverage.py

Validates that every custom Falco rule and OSquery schedule entry:
1. Has a MITRE ATT&CK tag (Txxxx format)
2. Maps to a known tactic tag (mitre_*)
3. New rules added for gap-closure are structurally present

This is a *static* configuration test — no live stack required.
"""

import re

# ── Falco ──────────────────────────────────────────────────────────────────────

# All rules we explicitly authored (not upstream overrides)
CUSTOM_RULE_NAMES = {
    "Unprivileged namespace or overlayfs exploit tooling",
    "Suspicious read of kernel exploit-sensitive files",
    "Suspicious write of kernel exploit-sensitive files",
    "SSH Outbound from Service Account",
    "Hijack Execution Flow with LD_PRELOAD",
    "Clear Command History (Truncate)",
    "Masquerading as Kernel Thread",
    "Reverse Shell Detection",
    "Web Server Spawned Shell",
    "Shadow File Read by Non-Auth Process",
    "Cross-User Bash History Access",
    "Security Tool Tampering",
    "Execution from Temporary Directory",
    "Suspicious File Permission Changes",
    "Credential Dumping Tool Execution",
    "Outbound Data Transfer via Common Tools",
    "DNS Query to Suspicious Resolver",
    "Kernel Module Manipulation",
    "Cron or At Job Creation by Non-Admin",
    "Package Repository Tampering",
    "Sysctl Kernel Parameter Modification",
}

# Rules that are overrides of upstream rules (have 'override' key) — must still have tags
OVERRIDE_RULE_NAMES = {
    "Drop and execute new binary in container",
    "Clear Log Activities",
}

MITRE_TECHNIQUE_RE = re.compile(r"^T\d{4}(\.\d{3})?$")

TACTIC_TAG_PREFIXES = {
    "mitre_execution",
    "mitre_persistence",
    "mitre_privilege_escalation",
    "mitre_defense_evasion",
    "mitre_credential_access",
    "mitre_discovery",
    "mitre_lateral_movement",
    "mitre_collection",
    "mitre_exfiltration",
    "mitre_command_and_control",
    "mitre_impact",
}


def _rules_by_name(falco_rules: list[dict]) -> dict[str, dict]:
    return {e["rule"]: e for e in falco_rules if "rule" in e}


def test_all_custom_rules_exist(falco_rules: list[dict]) -> None:
    """Every rule we authored must be present in the config."""
    present = set(_rules_by_name(falco_rules))
    missing = CUSTOM_RULE_NAMES - present
    assert not missing, f"Custom rules missing from falco_rules.local.yaml: {missing}"


def test_all_custom_rules_have_mitre_technique_tag(falco_rules: list[dict]) -> None:
    """Each custom rule must have at least one Txxxx MITRE technique tag."""
    rules = _rules_by_name(falco_rules)
    failures = []
    for name in CUSTOM_RULE_NAMES:
        entry = rules.get(name)
        if not entry:
            continue
        tags = entry.get("tags", [])
        has_technique = any(MITRE_TECHNIQUE_RE.match(str(t)) for t in tags)
        if not has_technique:
            failures.append(f"{name}: tags={tags}")
    assert not failures, "Rules missing MITRE Technique tags:\n" + "\n".join(failures)


def test_all_custom_rules_have_mitre_tactic_tag(falco_rules: list[dict]) -> None:
    """Each custom rule must have at least one mitre_<tactic> tag."""
    rules = _rules_by_name(falco_rules)
    failures = []
    for name in CUSTOM_RULE_NAMES:
        entry = rules.get(name)
        if not entry:
            continue
        tags = set(entry.get("tags", []))
        has_tactic = bool(tags & TACTIC_TAG_PREFIXES)
        if not has_tactic:
            failures.append(f"{name}: tags={sorted(tags)}")
    assert not failures, "Rules missing MITRE Tactic tags:\n" + "\n".join(failures)


def test_gap_closure_rules_all_present(falco_rules: list[dict]) -> None:
    """The four gap-closure rules from mitre_linux_coverage_gaps.md must be present."""
    gap_rules = {
        "SSH Outbound from Service Account",
        "Hijack Execution Flow with LD_PRELOAD",
        "Clear Command History (Truncate)",
        "Masquerading as Kernel Thread",
    }
    present = set(_rules_by_name(falco_rules))
    missing = gap_rules - present
    assert not missing, f"Gap-closure rules missing: {missing}"


def test_override_rules_have_mitre_tags(falco_rules: list[dict]) -> None:
    """Overriding upstream rules must also carry MITRE tags."""
    rules = _rules_by_name(falco_rules)
    failures = []
    for name in OVERRIDE_RULE_NAMES:
        entry = rules.get(name)
        if not entry:
            continue  # overrides may appear without full body — skip
        tags = entry.get("tags", [])
        has_technique = any(MITRE_TECHNIQUE_RE.match(str(t)) for t in tags)
        has_tactic = bool(set(tags) & TACTIC_TAG_PREFIXES)
        if not (has_technique or has_tactic):
            failures.append(f"{name}: tags={tags}")
    assert not failures, "Override rules missing MITRE tags:\n" + "\n".join(failures)


def test_ld_preload_rule_targets_execve(falco_rules: list[dict]) -> None:
    """LD_PRELOAD rule must use spawned_process to catch execve-based injection."""
    rules = _rules_by_name(falco_rules)
    rule = rules.get("Hijack Execution Flow with LD_PRELOAD", {})
    condition = rule.get("condition", "")
    assert "spawned_process" in condition, (
        "LD_PRELOAD rule should use spawned_process to catch execve"
    )
    assert "LD_PRELOAD" in condition


def test_masquerade_rule_targets_userspace_paths(falco_rules: list[dict]) -> None:
    """Masquerade rule must check for /tmp, /dev/shm, /var/tmp."""
    rules = _rules_by_name(falco_rules)
    rule = rules.get("Masquerading as Kernel Thread", {})
    condition = rule.get("condition", "")
    for path in ("/tmp/", "/dev/shm/", "/var/tmp/"):
        assert path in condition, f"Masquerade rule should block {path}"


def test_ssh_lateral_rule_blocks_service_accounts(falco_rules: list[dict]) -> None:
    """SSH lateral movement rule must list common service account names."""
    rules = _rules_by_name(falco_rules)
    rule = rules.get("SSH Outbound from Service Account", {})
    condition = rule.get("condition", "")
    for account in ("www-data", "postgres", "mysql"):
        assert account in condition, f"SSH rule should cover {account}"


def test_reverse_shell_rule_detects_shells_with_network(falco_rules: list[dict]) -> None:
    """Reverse shell rule must check for shell binaries with network connections."""
    rules = _rules_by_name(falco_rules)
    rule = rules.get("Reverse Shell Detection", {})
    condition = rule.get("condition", "")
    assert "spawned_process" in condition
    assert any(s in condition for s in ("bash", "sh", "dash")), "Should detect common shells"
    assert "fd.type" in condition, "Should check for network connections"


def test_shadow_read_rule_has_auth_process_allowlist(falco_rules: list[dict]) -> None:
    """Shadow read rule must allow known auth processes."""
    rules = _rules_by_name(falco_rules)
    rule = rules.get("Shadow File Read by Non-Auth Process", {})
    condition = rule.get("condition", "")
    for proc in ("sshd", "sudo", "su", "passwd"):
        assert proc in condition, f"Should allow {proc} to read shadow"


def test_security_tampering_rule_covers_key_tools(falco_rules: list[dict]) -> None:
    """Security tampering rule must cover falco, osquery, auditd, iptables."""
    rules = _rules_by_name(falco_rules)
    rule = rules.get("Security Tool Tampering", {})
    condition = rule.get("condition", "")
    for tool in ("falco", "osquery", "auditd", "iptables"):
        assert tool in condition, f"Should detect tampering with {tool}"


def test_tmp_execution_rule_covers_common_tmp_paths(falco_rules: list[dict]) -> None:
    """Tmp execution rule must check /tmp, /dev/shm, /var/tmp."""
    rules = _rules_by_name(falco_rules)
    rule = rules.get("Execution from Temporary Directory", {})
    condition = rule.get("condition", "")
    for path in ("/tmp/", "/dev/shm/", "/var/tmp/"):
        assert path in condition, f"Should detect execution from {path}"


def test_exfil_rule_detects_common_transfer_tools(falco_rules: list[dict]) -> None:
    """Exfiltration rule must detect curl, wget, scp, etc."""
    rules = _rules_by_name(falco_rules)
    rule = rules.get("Outbound Data Transfer via Common Tools", {})
    condition = rule.get("condition", "")
    for tool in ("curl", "wget", "scp"):
        assert tool in condition, f"Should detect {tool} for exfiltration"


def test_dns_tampering_rule_detects_resolv_conf_changes(falco_rules: list[dict]) -> None:
    """DNS tampering rule must detect /etc/resolv.conf writes."""
    rules = _rules_by_name(falco_rules)
    rule = rules.get("DNS Query to Suspicious Resolver", {})
    condition = rule.get("condition", "")
    assert "/etc/resolv.conf" in condition


def test_package_tampering_rule_detects_apt_sources(falco_rules: list[dict]) -> None:
    """Package tampering rule must detect APT sources modification."""
    rules = _rules_by_name(falco_rules)
    rule = rules.get("Package Repository Tampering", {})
    condition = rule.get("condition", "")
    assert "/etc/apt/sources" in condition


# ── OSquery ────────────────────────────────────────────────────────────────────

MITRE_TAG_IN_DESC_RE = re.compile(r"\[T\d{4}")

EXPECTED_FIM_QUERIES = {
    "file_events",
}

EXPECTED_FIM_FILE_PATHS = {
    "bash_profiles",
    "init_scripts",
}

EXPECTED_MITRE_TAGGED_QUERIES = {
    "crontab",
    "systemd_units",
    "suid_bin",
    "sudo_users",
    "kernel_modules",
    "authorized_keys",
    "docker_containers",
    "file_changes",
    "users",
}


def _schedule(config: dict) -> dict[str, dict]:
    return {
        k: v for k, v in config["schedule"].items()
        if not k.strip().startswith("//")
    }


def test_osquery_has_fim_file_events_query(osquery_primary_config: dict) -> None:
    """file_events query must be scheduled for FIM to function."""
    schedule = _schedule(osquery_primary_config)
    assert "file_events" in schedule, (
        "file_events query missing — OSquery FIM will not fire"
    )


def test_osquery_has_fim_file_paths_block(osquery_primary_config: dict) -> None:
    """file_paths block must exist with bash_profiles and init_scripts sections."""
    file_paths = osquery_primary_config.get("file_paths", {})
    assert file_paths, "file_paths block missing from osqueryd.conf"
    missing = EXPECTED_FIM_FILE_PATHS - set(file_paths)
    assert not missing, f"FIM path groups missing: {missing}"


def test_osquery_fim_covers_bash_history(osquery_primary_config: dict) -> None:
    """FIM must monitor .bash_history for history-clearing detection."""
    file_paths = osquery_primary_config.get("file_paths", {})
    bash = file_paths.get("bash_profiles", [])
    has_history = any(".bash_history" in p for p in bash)
    assert has_history, ".bash_history not in FIM file_paths.bash_profiles"


def test_osquery_fim_covers_etc_shadow(osquery_primary_config: dict) -> None:
    """Critical-file query must poll /etc/shadow for credential access detection."""
    schedule = _schedule(osquery_primary_config)
    query = schedule.get("file_changes", {}).get("query", "")
    assert "/etc/shadow" in query, "/etc/shadow missing from file_changes query"


def test_osquery_mitre_tagged_queries_have_tag_in_description(
    osquery_primary_config: dict,
) -> None:
    """Core detection queries must have a MITRE [Txxxx] tag in their description."""
    schedule = _schedule(osquery_primary_config)
    untagged = []
    for qname in EXPECTED_MITRE_TAGGED_QUERIES:
        entry = schedule.get(qname)
        if not entry:
            untagged.append(f"{qname}: MISSING")
            continue
        desc = entry.get("description", "")
        if not MITRE_TAG_IN_DESC_RE.search(desc):
            untagged.append(f"{qname}: '{desc}'")
    assert not untagged, (
        "OSquery queries missing MITRE tags in description:\n" + "\n".join(untagged)
    )


def test_osquery_process_envs_monitors_ld_preload(osquery_primary_config: dict) -> None:
    """process_envs query must monitor LD_PRELOAD for T1574.006 detection."""
    schedule = _schedule(osquery_primary_config)
    query = schedule.get("process_envs", {}).get("query", "")
    assert "LD_PRELOAD" in query, "process_envs must monitor LD_PRELOAD"


def test_alert_definitions_reference_correct_streams() -> None:
    """Alert JSON must target existing stream names, not generic 'default'."""
    import json
    from pathlib import Path

    alerts_file = Path(__file__).resolve().parents[1] / "alerts/openobserve/alerts.json"
    if not alerts_file.exists():
        return  # Optional: only validate if file is present

    alerts = json.loads(alerts_file.read_text())
    valid_streams = {"falco", "clamav", "osquery", "system-logs"}
    for alert in alerts:
        stream = alert.get("stream_name", "")
        assert stream in valid_streams, (
            f"Alert '{alert.get('name')}' targets stream '{stream}' "
            f"— expected one of {valid_streams}"
        )
