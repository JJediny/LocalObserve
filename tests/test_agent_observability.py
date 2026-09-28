"""Static validation of the AI agent session capture configuration (issue #91).

Validates, without a live stack:
  * the OTel collector config wires the agent pipeline correctly
    (filter drop semantics, redaction processor, stream routing)
  * every Sigma rule in active_rules is well-formed with unique IDs
  * the ai_agent rules use the required logsource and Sigma idiom fields
  * the field-mapping pipeline maps the flattened gen_ai attributes
  * the dashboard and alert definitions parse and reference the right streams
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

AGENT_LOGSOURCE = {"product": "ai_agent", "service": "otel"}
AGENT_STREAM = "agent_logs"  # OpenObserve sanitizes dashes to underscores


@pytest.fixture(scope="module")
def collector_config(repo_root: Path) -> dict:
    return yaml.safe_load((repo_root / "otel-collector-config.yaml").read_text())


@pytest.fixture(scope="module")
def active_sigma_rules(repo_root: Path) -> list[dict]:
    rules = []
    for path in sorted((repo_root / "rules" / "sigma" / "active_rules").glob("*.yaml")):
        rules.append({"path": path, "rule": yaml.safe_load(path.read_text())})
    return rules


@pytest.fixture(scope="module")
def sigma_pipeline(repo_root: Path) -> dict:
    return yaml.safe_load(
        (repo_root / "rules" / "sigma" / "pipelines" / "localobserve_pipeline.yaml").read_text()
    )


class TestCollectorAgentPipeline:
    def test_agent_pipeline_exists(self, collector_config: dict) -> None:
        pipelines = collector_config["service"]["pipelines"]
        assert "logs/ai_agent" in pipelines, "logs/ai_agent pipeline missing"

    def test_agent_pipeline_routes_to_dedicated_stream(self, collector_config: dict) -> None:
        exporters = collector_config["service"]["pipelines"]["logs/ai_agent"]["exporters"]
        assert "otlp_http/openobserve_agent_logs" in exporters
        exporter = collector_config["exporters"]["otlp_http/openobserve_agent_logs"]
        assert exporter["headers"]["stream-name"] == "agent-logs"

    def test_agent_pipeline_feeds_rsigma(self, collector_config: dict) -> None:
        exporters = collector_config["service"]["pipelines"]["logs/ai_agent"]["exporters"]
        assert "otlp_http/rsigma" in exporters, "agent logs must reach rsigma for detection"

    def test_generic_pipeline_excludes_agent_logs(self, collector_config: dict) -> None:
        processors = collector_config["service"]["pipelines"]["logs/otlp"]["processors"]
        assert "filter/drop_agent_logs" in processors

    def test_agent_pipeline_excludes_non_agent_logs(self, collector_config: dict) -> None:
        processors = collector_config["service"]["pipelines"]["logs/ai_agent"]["processors"]
        assert "filter/drop_non_agent_logs" in processors

    def test_filters_use_drop_semantics(self, collector_config: dict) -> None:
        """Filter processor conditions are DROP conditions (v0.146+ *_conditions format).

        Empirically validated against otelcol-contrib 0.152.0: the legacy
        `logs: log_record:` form silently dropped ALL records (bare conditions
        like 'true' matched everything), so the new `log_conditions` form with
        inverted semantics is required.
        """
        drop_agents = collector_config["processors"]["filter/drop_agent_logs"]
        assert "log_conditions" in drop_agents
        assert any('== "ai-agents"' in c for c in drop_agents["log_conditions"])

        drop_non_agents = collector_config["processors"]["filter/drop_non_agent_logs"]
        assert "log_conditions" in drop_non_agents
        assert any('!= "ai-agents"' in c for c in drop_non_agents["log_conditions"])

    def test_redaction_processor_strips_prompts_by_default(self, collector_config: dict) -> None:
        redact = collector_config["processors"]["transform/agent_redact"]
        statements = [s for block in redact["log_statements"] for s in block["statements"]]
        deleted_keys = [s for s in statements if s.startswith("delete_key")]
        assert any('"gen_ai.prompt"' in s for s in deleted_keys)
        assert any('"gen_ai.completion"' in s for s in deleted_keys)
        # Opt-out condition: only redact when capture is not explicitly enabled
        conditions = [c for block in redact["log_statements"] for c in block.get("conditions", [])]
        assert any("ai.capture_prompts" in c for c in conditions)

    def test_metrics_pipeline_has_no_debug_exporter(self, collector_config: dict) -> None:
        exporters = collector_config["service"]["pipelines"]["metrics"]["exporters"]
        assert "debug" not in exporters, "debug exporter in metrics pipeline is pure overhead"


class TestAgentSigmaRules:
    def test_agent_rules_exist(self, active_sigma_rules: list[dict]) -> None:
        agent_rules = [
            r for r in active_sigma_rules
            if r["rule"].get("logsource", {}).get("product") == "ai_agent"
        ]
        assert len(agent_rules) >= 5, "expected at least 5 AI agent rules"

    def test_agent_rules_use_agent_logsource(self, active_sigma_rules: list[dict]) -> None:
        for entry in active_sigma_rules:
            rule = entry["rule"]
            if "ai" in entry["path"].name and rule.get("logsource") != AGENT_LOGSOURCE:
                pytest.fail(
                    f"{entry['path'].name}: ai_agent rules must use logsource {AGENT_LOGSOURCE}"
                )

    def test_all_rules_have_required_fields(self, active_sigma_rules: list[dict]) -> None:
        required = {"title", "id", "level", "status", "description", "detection", "logsource"}
        for entry in active_sigma_rules:
            missing = required - set(entry["rule"].keys())
            assert not missing, f"{entry['path'].name} missing: {missing}"

    def test_rule_ids_unique(self, active_sigma_rules: list[dict]) -> None:
        ids = [entry["rule"]["id"] for entry in active_sigma_rules]
        assert len(ids) == len(set(ids)), "duplicate Sigma rule IDs detected"

    def test_detection_condition_references_defined_selections(
        self, active_sigma_rules: list[dict]
    ) -> None:
        for entry in active_sigma_rules:
            detection = entry["rule"]["detection"]
            condition = detection["condition"]
            for word in condition.replace("(", " ").replace(")", " ").split():
                if word in ("and", "or", "not", "1", "of", "them", "all"):
                    continue
                assert word in detection, (
                    f"{entry['path'].name}: condition references undefined selection '{word}'"
                )

    def test_agent_rules_match_flattened_attributes(
        self, active_sigma_rules: list[dict], sigma_pipeline: dict
    ) -> None:
        """The pipeline must map the flattened gen_ai attrs onto Sigma idiom fields."""
        transforms = sigma_pipeline["transformations"]
        agent_mapping = None
        for t in transforms:
            conds = t.get("rule_conditions", [])
            if any(
                c.get("product") == "ai_agent" and c.get("service") == "otel" for c in conds
            ):
                agent_mapping = t
        assert agent_mapping is not None, "ai_agent field mapping missing from pipeline"
        mapping = agent_mapping["mapping"]
        assert mapping.get("CommandLine") == "gen_ai_tool_args"
        assert mapping.get("Image") == "gen_ai_tool_name"


class TestDashboardAndAlerts:
    def test_dashboard_parses_and_references_agent_stream(self, repo_root: Path) -> None:
        dash = json.loads(
            (repo_root / "dashboards" / "openobserve" / "AI_Agent_Sessions.json").read_text()
        )
        assert dash["title"] == "AI Agent Sessions"
        panels = dash["tabs"][0]["panels"]
        assert len(panels) >= 5
        agent_stream_queries = [
            p for p in panels if AGENT_STREAM in p["queries"][0]["query"]
        ]
        assert len(agent_stream_queries) >= 5, "dashboard must query the agent_logs stream"

    def test_dashboard_variables(self, repo_root: Path) -> None:
        dash = json.loads(
            (repo_root / "dashboards" / "openobserve" / "AI_Agent_Sessions.json").read_text()
        )
        var_names = [v["name"] for v in dash["variables"]["list"]]
        assert "service" in var_names
        assert "session" in var_names

    def test_agent_alerts_defined(self, repo_root: Path) -> None:
        alerts = json.loads((repo_root / "alerts" / "openobserve" / "alerts.json").read_text())
        names = {a["name"] for a in alerts}
        assert "AIAgent-Sensitive-File-Access" in names
        assert "AIAgent-Tool-Error-Spike" in names
        for alert in alerts:
            if alert["name"].startswith("AIAgent-"):
                assert alert["stream_name"] == AGENT_STREAM
