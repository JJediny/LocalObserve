from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = REPO_ROOT / ".data" / "coverage" / "caldera_detection_coverage.json"

SAFE_ABILITIES = [
    "52177cc1-b9ab-4411-ac21-2eadc4b5d3b8",
    "6e1a53c0-7352-4899-be35-fa7f364d5722",
    "335cea7b-bec0-48c6-adfb-6066070f5f68",
    "5a39d7ed-45c9-4a79-b581-e5fb99e24f65",
    "5c4dd985-89e3-4590-9b57-71fed66ff4e2",
    "422526ec-27e9-429a-995b-c686a29561a4",
    "43b3754c-def4-4699-a673-1d85648fda6a",
    "a0676fe1-cd52-482e-8dde-349b73f9aa69",
]
PAYLOAD_ABILITY = "a0676fe1-cd52-482e-8dde-349b73f9aa69"
DUMP_HISTORY_ABILITY = "422526ec-27e9-429a-995b-c686a29561a4"
AVOID_LOGS_ABILITY = "43b3754c-def4-4699-a673-1d85648fda6a"


def _load_falco_rules() -> list[dict[str, Any]]:
    return yaml.safe_load((REPO_ROOT / "falco_rules.local.yaml").read_text(encoding="utf-8"))


def _falco_rule_names() -> set[str]:
    return {entry["rule"] for entry in _load_falco_rules() if isinstance(entry, dict) and "rule" in entry}


def _config_expectations_for_ability(ability_id: str) -> list[dict[str, Any]]:
    expectations = [
        {
            "category": "trace",
            "source": "otel",
            "name": "openobserve-trace-search",
            "expected": True,
            "reason": "every safe ability should emit a searchable OTEL trace",
        }
    ]
    if ability_id == PAYLOAD_ABILITY:
        expectations.append(
            {
                "category": "config",
                "source": "falco_rules.local.yaml",
                "name": "Execution from Temporary Directory",
                "expected": "Execution from Temporary Directory" in _falco_rule_names(),
                "reason": "payload-backed ability is expected to map to the temp-execution Falco rule",
            }
        )
        expectations.append(
            {
                "category": "live_log",
                "source": "falco",
                "name": "Execution from Temporary Directory",
                "expected": True,
                "reason": "payload-backed ability should produce a matching Falco event",
            }
        )
    if ability_id == DUMP_HISTORY_ABILITY:
        expectations.append(
            {
                "category": "config",
                "source": "falco_rules.local.yaml",
                "name": "Cross-User Bash History Access",
                "expected": "Cross-User Bash History Access" in _falco_rule_names(),
                "reason": "dump-history should map to the bash history access Falco rule",
            }
        )
        expectations.append(
            {
                "category": "live_log",
                "source": "falco",
                "name": "Cross-User Bash History Access",
                "expected": True,
                "reason": "dump-history should produce a matching Falco event",
            }
        )
    if ability_id == AVOID_LOGS_ABILITY:
        expectations.append(
            {
                "category": "config",
                "source": "falco_rules.local.yaml",
                "name": "Clear Command History (Truncate)",
                "expected": "Clear Command History (Truncate)" in _falco_rule_names(),
                "reason": "avoid-logs should map to the history truncation Falco rule",
            }
        )
        expectations.append(
            {
                "category": "live_log",
                "source": "falco",
                "name": "Clear Command History (Truncate)",
                "expected": True,
                "reason": "avoid-logs should produce a matching Falco event",
            }
        )
        expectations.append(
            {
                "category": "config",
                "source": "osqueryd.conf",
                "name": "file_events bash_profiles coverage",
                "expected": True,
                "reason": "osquery FIM should be configured to watch .bash_history through bash_profiles",
            }
        )
        expectations.append(
            {
                "category": "live_query",
                "source": "osqueryi",
                "name": "file query sees .bash_history",
                "expected": True,
                "reason": "osquery local file query should confirm the observed .bash_history path exists",
            }
        )
    return expectations


def build_coverage_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    per_ability: list[dict[str, Any]] = []
    total_expected = 0
    total_verified = 0
    totals_by_category: dict[str, dict[str, int]] = {}

    for payload in results:
        ability_id = payload["ability_id"]
        config_expectations = _config_expectations_for_ability(ability_id)
        evaluations: list[dict[str, Any]] = []

        for expectation in config_expectations:
            verified = False
            if expectation["category"] == "trace":
                verified = bool(payload["trace"].get("verified"))
            elif expectation["category"] == "config":
                if expectation["name"] == "file_events bash_profiles coverage":
                    verified = any(
                        ".bash_history" in path
                        for path in payload.get("osquery", {}).get("config", {}).get("bash_profiles", [])
                    )
                else:
                    verified = bool(expectation["expected"])
            elif expectation["category"] == "live_log":
                verified = bool(payload["correlation"]["streams"].get("falco", {}).get("verified"))
            elif expectation["category"] == "live_query":
                verified = bool(payload.get("osquery", {}).get("live_query", {}).get("verified"))

            evaluations.append({**expectation, "verified": verified})

            if expectation["expected"]:
                total_expected += 1
                if verified:
                    total_verified += 1

                category_totals = totals_by_category.setdefault(
                    expectation["category"],
                    {"expected": 0, "verified": 0},
                )
                category_totals["expected"] += 1
                if verified:
                    category_totals["verified"] += 1

        per_ability.append(
            {
                "ability_id": ability_id,
                "ability_name": payload["ability_name"],
                "technique_id": payload["technique_id"],
                "payloads": payload["payloads"],
                "evaluations": evaluations,
            }
        )

    coverage_percent = (total_verified / total_expected * 100.0) if total_expected else 0.0
    categories = {
        category: {
            **counts,
            "coverage_percent": (counts["verified"] / counts["expected"] * 100.0) if counts["expected"] else 0.0,
        }
        for category, counts in totals_by_category.items()
    }
    return {
        "safe_ability_count": len(results),
        "total_expected_signals": total_expected,
        "total_verified_signals": total_verified,
        "coverage_percent": coverage_percent,
        "categories": categories,
        "abilities": per_ability,
    }


def write_coverage_report(report: dict[str, Any]) -> Path:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return ARTIFACT_PATH



# ---------------------------------------------------------------------------
# Telemetry stream schema validation
# ---------------------------------------------------------------------------
REQUIRED_STREAM_SCHEMA_FIELDS: dict[str, list[str]] = {
    "falco": [
        "rule",
        "output",
        "priority",
        "output_fields",
        "_timestamp",
    ],
    "default": [
        "service_name",
        "operation_name",
        "trace_id",
        "span_id",
        "_timestamp",
    ],
}


def validate_stream_schema(stream_name: str, hits: list[dict[str, Any]], required_fields: list[str] | None = None) -> list[str]:
    """Return a list of missing required fields from the first hit in a stream.

    If *required_fields* is not provided, uses the built-in
    REQUIRED_STREAM_SCHEMA_FIELDS mapping keyed by *stream_name*.
    Returns an empty list when all required fields are present.
    Returns all required fields when there are no hits.
    """
    if required_fields is None:
        required_fields = REQUIRED_STREAM_SCHEMA_FIELDS.get(stream_name, [])
    if not hits:
        return list(required_fields)
    first_hit = hits[0]
    return [field for field in required_fields if field not in first_hit]
