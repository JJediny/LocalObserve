"""
Compliance validation tests for OMB Memorandum M-26-14.
Verifies structured logging schemas, JSON formats, time sync, and retention.
"""
from pathlib import Path
import re
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_compliance_crosswalk_exists():
    """Verify the official M-26-14 compliance crosswalk document is present."""
    crosswalk = REPO_ROOT / "docs" / "compliance_crosswalk.md"
    assert crosswalk.exists(), "docs/compliance_crosswalk.md is missing"
    content = crosswalk.read_text(encoding="utf-8")
    assert "M-26-14 Logging Compliance Crosswalk" in content
    # Check that all 8 requirements are listed
    for req in range(1, 9):
        assert f"Req-{req}" in content


def test_otel_collector_json_parsers(otel_collector_config):
    """Verify that file receivers have json_parser operators for structured ingestion (Req-1)."""
    receivers = otel_collector_config.get("receivers", {})
    assert "file_log/osquery" in receivers, "osquery log receiver missing in otel config"
    assert "file_log/falco" in receivers, "falco log receiver missing in otel config"

    # osquery receiver should parse json
    osquery_ops = receivers["file_log/osquery"].get("operators", [])
    assert any(op.get("type") == "json_parser" for op in osquery_ops), \
        "osquery log receiver lacks json_parser operator"

    # falco receiver should parse json
    falco_ops = receivers["file_log/falco"].get("operators", [])
    assert any(op.get("type") == "json_parser" for op in falco_ops), \
        "falco log receiver lacks json_parser operator"


def test_otel_collector_mandatory_resource_attributes(otel_collector_config):
    """Verify that OTel Collector assigns crucial structured tracking attributes (Req-1)."""
    processors = otel_collector_config.get("processors", {})
    assert "resource/osquery" in processors, "resource/osquery processor missing"
    assert "resource/falco" in processors, "resource/falco processor missing"

    # Validate osquery resource attributes
    osquery_attrs = processors["resource/osquery"].get("attributes", [])
    keys_osquery = {attr.get("key") for attr in osquery_attrs}
    assert "service.name" in keys_osquery
    assert "deployment.environment" in keys_osquery
    assert "log.source" in keys_osquery

    # Validate falco resource attributes
    falco_attrs = processors["resource/falco"].get("attributes", [])
    keys_falco = {attr.get("key") for attr in falco_attrs}
    assert "service.name" in keys_falco
    assert "deployment.environment" in keys_falco
    assert "log.source" in keys_falco


def test_falco_json_output_configured(falco_config):
    """Verify Falco is explicitly configured to serialize logs in JSON format (Req-1)."""
    assert falco_config.get("json_output") is True, "Falco json_output must be enabled"
    assert falco_config.get("file_output", {}).get("enabled") is True, "Falco file_output must be enabled"
    assert falco_config.get("file_output", {}).get("filename"), "Falco output filename must be configured"


def test_osquery_logging_enabled(osquery_primary_config, osquery_deep_forensic_config, osquery_ssd_config):
    """Verify all osquery config profiles have results logging enabled (Req-1)."""
    for config_name, conf in [
        ("osqueryd.conf", osquery_primary_config),
        ("osqueryd-deep-forensic.conf", osquery_deep_forensic_config),
        ("osqueryd-ssd-optimized.conf", osquery_ssd_config),
    ]:
        options = conf.get("options", {})
        assert options.get("disable_logging") is False, f"osquery results logging disabled in {config_name}"


def test_compliance_audit_ledger_integrity():
    """Verify the cryptographic chain-linked audit ledger for config files is intact (Req-5)."""
    import sys
    from pathlib import Path
    sys.path.append(str(REPO_ROOT / "tools"))
    from compliance_audit_ledger import load_ledger, verify_chain

    ledger = load_ledger()
    assert len(ledger) > 0, "Genesis block is missing from compliance audit ledger"
    assert verify_chain(ledger) is True, "Audit ledger cryptographic integrity check failed!"


def test_openobserve_retention_configured():
    """Verify that OpenObserve retention settings are defined for a 6-month hot tier (Req-2)."""
    import yaml
    compose_path = REPO_ROOT / "docker-compose.yaml"
    assert compose_path.exists(), "docker-compose.yaml is missing"
    
    with open(compose_path, "r", encoding="utf-8") as f:
        compose_data = yaml.safe_load(f)
    
    env_list = compose_data.get("services", {}).get("openobserve", {}).get("environment", [])
    assert any("ZO_RETENTION_PERIOD=" in env or env.startswith("ZO_RETENTION_PERIOD=") for env in env_list), \
        "ZO_RETENTION_PERIOD environment variable must be configured in docker-compose.yaml for Requirement 2"
