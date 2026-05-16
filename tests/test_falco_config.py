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


def test_falco_config_loads_as_mapping(falco_config: dict) -> None:
    assert isinstance(falco_config, dict)
    assert falco_config


def test_falco_config_uses_expected_rule_sources(falco_config: dict) -> None:
    rules_files = falco_config["rules_files"]

    assert "/etc/falco/falco_rules.yaml" in rules_files
    assert "/etc/falco/falco_rules.local.yaml" in rules_files
    assert "/etc/falco/rules.d" in rules_files


def test_falco_config_keeps_local_runtime_defaults(falco_config: dict) -> None:
    assert falco_config["engine"]["kind"] == "modern_ebpf"
    assert falco_config["priority"].upper() in ALLOWED_PRIORITIES
    assert falco_config["priority"].lower() == "warning"
    assert falco_config["buffered_outputs"] is True
    assert falco_config["json_output"] is True
    assert falco_config["log_stderr"] is True
    assert falco_config["log_syslog"] is False


def test_falco_config_writes_and_forwards_events(falco_config: dict) -> None:
    file_output = falco_config["file_output"]
    stdout_output = falco_config["stdout_output"]
    http_output = falco_config["http_output"]

    assert file_output["enabled"] is True
    assert file_output["filename"] == "/var/log/falco/events.jsonl"
    assert stdout_output["enabled"] is True
    assert http_output["enabled"] is True
    assert http_output["url"] == "http://falcosidekick:2801"


def test_falco_config_disables_unused_syslog_output(falco_config: dict) -> None:
    assert falco_config["syslog_output"]["enabled"] is False
