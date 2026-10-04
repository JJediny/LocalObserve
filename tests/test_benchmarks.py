"""Validation of the benchmark harness and resource budgets (Part A of the plan).

Static checks that keep tools/bench_budgets.json and the compose logging caps
honest. The live benchmark itself is run via `task bench` (tools/bench_stack.py).
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml


def test_budgets_file_is_valid(repo_root: Path) -> None:
    budgets = json.loads((repo_root / "tools" / "bench_budgets.json").read_text())
    assert budgets["ram_mib"], "per-service RAM budgets missing"
    assert budgets["stack_ram_mib_total"] > 0
    assert budgets["stack_write_mib_per_min_total"] > 0

    known_services = {
        "openobserve", "otel-collector", "falco", "osquery", "rsigma", "alert-receiver",
    }
    assert known_services.issubset(set(budgets["ram_mib"])), (
        "RAM budgets must cover every always-on service"
    )

    # Budgets must respect compose limits (they are ceilings below mem_limit)
    compose = yaml.safe_load((repo_root / "docker-compose.yaml").read_text())
    for service, budget in budgets["ram_mib"].items():
        svc = compose["services"].get(service)
        assert svc is not None, f"budget references unknown service {service}"
        mem_limit = svc.get("mem_limit")
        if mem_limit:
            raw = str(mem_limit)
            multipliers = {"g": 1024, "m": 1, "k": 1 / 1024}
            limit_mib = float(raw.rstrip("gmk")) * multipliers[raw[-1].lower()]
            assert budget <= limit_mib, (
                f"{service}: RAM budget {budget} MiB exceeds compose mem_limit {raw}"
            )


def test_always_on_services_have_log_caps(repo_root: Path) -> None:
    """Every always-on service must cap Docker json-file log growth (SSD wear)."""
    compose = yaml.safe_load((repo_root / "docker-compose.yaml").read_text())
    profile_gated = {
        # On-demand services (scan/gpu/netflow profiles) are exempt from the
        # always-on SSD budget; they get caps when their profile is exercised.
        name for name, svc in compose["services"].items() if svc.get("profiles")
    }
    for name, svc in compose["services"].items():
        if name in profile_gated:
            continue
        logging_cfg = svc.get("logging")
        assert logging_cfg, f"service {name} has no logging cap (SSD wear risk)"
        assert logging_cfg.get("driver") == "json-file"
        opts = logging_cfg.get("options", {})
        assert "max-size" in opts and "max-file" in opts, (
            f"service {name} logging cap missing max-size/max-file"
        )


def test_falco_does_not_duplicate_events_to_stdout(repo_root: Path) -> None:
    """Falco must not write every event to both the JSONL file and stdout.

    file_output feeds the OTel collector; stdout feeds Docker's json-file log.
    Both together double the per-event SSD writes.
    """
    config = yaml.safe_load((repo_root / "falco-config.yaml").read_text())
    assert config["file_output"]["enabled"] is True
    assert config["stdout_output"]["enabled"] is False, (
        "falco stdout_output duplicates every event into the Docker log (SSD wear)"
    )


def test_osquery_config_is_selectable(repo_root: Path) -> None:
    """The compose file must allow selecting the osquery profile via OSQUERY_CONFIG."""
    compose_text = (repo_root / "docker-compose.yaml").read_text()
    assert "${OSQUERY_CONFIG:-osqueryd.conf}:/etc/osquery/osquery.conf:ro" in compose_text
    # And all referenced profiles must exist
    for profile in (
        "osqueryd.conf",
        "osqueryd-ssd-optimized.conf",
        "osqueryd-deep-forensic.conf",
    ):
        assert (repo_root / profile).exists(), f"referenced osquery profile missing: {profile}"


def test_logrotate_config_covers_tailed_files(repo_root: Path) -> None:
    """Every file the OTel collector tails must be rotated (unbounded growth otherwise).

    The collector tails container-visible paths (e.g. /var/log/falco/events.jsonl)
    which are bind mounts of host paths under ./.data; logrotate runs on the host
    against the ./.data paths, so compare basenames under the expected host dirs.
    """
    collector = yaml.safe_load((repo_root / "otel-collector-config.yaml").read_text())
    tailed: set[str] = set()
    for receiver in collector["receivers"].values():
        if isinstance(receiver, dict) and "include" in receiver:
            tailed.update(receiver["include"])

    # Map container paths -> host ./.data paths (mirrors docker-compose mounts)
    container_to_host = {
        "/var/log/osquery": ".data/osquery",
        "/var/log/falco": ".data/falco",
        "/var/log/clamav": ".data/clamav",
        "/var/log/goflow2": ".data/goflow2",
    }
    logrotate = (repo_root / "scripts" / "logrotate-localobserve.conf").read_text()
    for path in tailed:
        container_dir, _, filename = path.rpartition("/")
        host_dir = container_to_host.get(container_dir)
        if host_dir is None:
            continue  # host-mounted system logs are rotated by the OS (news/syslog)
        host_path = f"{host_dir}/{filename}"
        assert host_path in logrotate, (
            f"collector tails {path} (host: {host_path}) but logrotate does not cover it"
        )


def test_bench_harness_scripts_exist(repo_root: Path) -> None:
    for tool in ("bench_stack.py", "bench_compare.py", "bench_budgets.json"):
        assert (repo_root / "tools" / tool).exists(), f"missing benchmark tool: {tool}"


def test_prometheus_scrape_is_not_too_hot(repo_root: Path) -> None:
    """openobserve-internals scrape interval must be >= 30s (write amplification)."""
    collector = yaml.safe_load((repo_root / "otel-collector-config.yaml").read_text())
    scrape_configs = collector["receivers"]["prometheus"]["config"]["scrape_configs"]
    oo_scrape = next(s for s in scrape_configs if s["job_name"] == "openobserve-internals")
    interval = oo_scrape["scrape_interval"]
    seconds = int(str(interval).rstrip("s"))
    assert seconds >= 30, f"scrape interval {interval} is too aggressive for steady-state writes"


def test_metrics_pipeline_drops_histogram_buckets(repo_root: Path) -> None:
    """Metrics pipeline must drop *_bucket series to cap steady-state write amplification (Issue #97)."""
    collector = yaml.safe_load((repo_root / "otel-collector-config.yaml").read_text())
    processors = collector.get("processors", {})
    assert "filter/drop_histogram_buckets" in processors, (
        "filter/drop_histogram_buckets processor missing in otel-collector-config.yaml"
    )
    drop_proc = processors["filter/drop_histogram_buckets"]
    conditions = drop_proc.get("metric_conditions", [])
    assert any(".*_bucket$" in c for c in conditions), (
        "filter/drop_histogram_buckets must drop metric.name matching .*_bucket$"
    )
    pipeline_procs = collector["service"]["pipelines"]["metrics"]["processors"]
    assert "filter/drop_histogram_buckets" in pipeline_procs, (
        "filter/drop_histogram_buckets must be included in service.pipelines.metrics.processors"
    )
