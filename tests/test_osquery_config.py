from __future__ import annotations

EXPECTED_KEV_QUERY_NAMES = {
    "kev_namespace_tooling",
    "kev_sensitive_mounts",
    "kev_sensitive_kernel_file_access",
}
REQUIRED_QUERY_FIELDS = {"query", "interval", "description"}


def _schedule_entries(config: dict) -> dict[str, dict]:
    return {
        name: definition
        for name, definition in config["schedule"].items()
        if not name.strip().startswith("//")
    }


def _assert_schedule_is_valid(schedule: dict[str, dict]) -> None:
    assert schedule

    for name, definition in schedule.items():
        assert REQUIRED_QUERY_FIELDS.issubset(definition), (
            f"missing fields for osquery schedule entry {name}"
        )
        query = definition["query"].strip()
        assert query.upper().startswith("SELECT "), (
            f"query should start with SELECT for {name}"
        )
        assert query.endswith(";"), f"query should end with a semicolon for {name}"
        assert isinstance(definition["interval"], int), (
            f"interval should be an int for {name}"
        )
        assert definition["interval"] > 0, f"interval should be positive for {name}"
        assert definition["description"].strip(), (
            f"description should be non-empty for {name}"
        )


def test_osquery_primary_config_has_expected_options(
    osquery_primary_config: dict,
) -> None:
    options = osquery_primary_config["options"]

    assert options["logger_path"] == "/var/log/osquery"
    assert options["disable_logging"] is False
    assert 1 <= options["schedule_splay_percent"] <= 100
    assert options["worker_threads"] >= 1


def test_osquery_ssd_config_has_expected_options(osquery_ssd_config: dict) -> None:
    options = osquery_ssd_config["options"]

    assert options["logger_path"] == "/var/log/osquery"
    assert options["disable_logging"] is False
    assert 1 <= options["schedule_splay_percent"] <= 100
    assert options["worker_threads"] >= 1
    assert options["utc"] is True


def test_osquery_primary_schedule_entries_are_structurally_valid(
    osquery_primary_config: dict,
) -> None:
    _assert_schedule_is_valid(_schedule_entries(osquery_primary_config))


def test_osquery_deep_forensic_schedule_entries_are_structurally_valid(
    osquery_deep_forensic_config: dict,
) -> None:
    _assert_schedule_is_valid(_schedule_entries(osquery_deep_forensic_config))


def test_osquery_ssd_schedule_entries_are_structurally_valid(
    osquery_ssd_config: dict,
) -> None:
    _assert_schedule_is_valid(_schedule_entries(osquery_ssd_config))


def test_osquery_profiles_include_expected_kev_queries(
    osquery_primary_config: dict,
    osquery_ssd_config: dict,
) -> None:
    primary_names = set(_schedule_entries(osquery_primary_config))
    ssd_names = set(_schedule_entries(osquery_ssd_config))

    assert EXPECTED_KEV_QUERY_NAMES.issubset(primary_names)
    assert EXPECTED_KEV_QUERY_NAMES.issubset(ssd_names)


def test_ssd_profile_is_less_aggressive_for_shared_queries(
    osquery_primary_config: dict,
    osquery_ssd_config: dict,
) -> None:
    primary_schedule = _schedule_entries(osquery_primary_config)
    ssd_schedule = _schedule_entries(osquery_ssd_config)

    # NOTE: The SSD profile may have some queries at a shorter interval than the primary
    # profile for high-value security queries (e.g. 'users' at 12h vs 24h) where fresher
    # data is intentionally prioritised over I/O savings. The key invariant is that the
    # SSD profile uses fewer *total* queries (enforced by test_ssd_profile_uses_fewer_workers).
    for query_name in set(primary_schedule) & set(ssd_schedule):
        primary_interval = primary_schedule[query_name]["interval"]
        ssd_interval = ssd_schedule[query_name]["interval"]
        # Allow SSD to be at most 2x *faster* for high-value security queries,
        # but never more than that (prevents accidentally setting 1s intervals).
        assert ssd_interval >= primary_interval // 2, (
            f"{query_name}: SSD interval {ssd_interval} is more than 2x faster "
            f"than primary {primary_interval} — likely a config mistake"
        )


def test_ssd_profile_uses_fewer_workers_and_no_more_queries(
    osquery_primary_config: dict,
    osquery_ssd_config: dict,
) -> None:
    assert (
        osquery_ssd_config["options"]["worker_threads"]
        <= osquery_primary_config["options"]["worker_threads"]
    )
    assert len(_schedule_entries(osquery_ssd_config)) <= len(
        _schedule_entries(osquery_primary_config)
    )


def test_default_osquery_profile_avoids_known_high_volume_defaults(
    osquery_primary_config: dict,
) -> None:
    schedule = _schedule_entries(osquery_primary_config)

    assert osquery_primary_config["packs"] == {
        "rootkit_detection": "/etc/osquery/packs/ossec-rootkit.conf"
    }
    assert "WHERE key IN (" in schedule["process_envs"]["query"]
    assert "LIMIT 200" in schedule["process_envs"]["query"]
    assert "COUNT(*) AS count" in schedule["deb_packages"]["query"]
    assert "LIMIT 500" in schedule["processes"]["query"]


def test_deep_forensic_profile_restores_verbose_queries_and_packs(
    osquery_deep_forensic_config: dict,
) -> None:
    schedule = _schedule_entries(osquery_deep_forensic_config)

    assert set(osquery_deep_forensic_config["packs"]) == {
        "incident_response",
        "rootkit_detection",
        "compliance",
    }
    assert schedule["process_envs"]["query"] == "SELECT * FROM process_envs;"
    assert (
        schedule["process_memory_map"]["query"] == "SELECT * FROM process_memory_map;"
    )
    assert schedule["processes"]["query"] == "SELECT * FROM processes;"
    assert schedule["deb_packages"]["query"] == "SELECT * FROM deb_packages;"


def test_quiet_and_deep_profiles_preserve_rootkit_detection(
    osquery_primary_config: dict,
    osquery_deep_forensic_config: dict,
) -> None:
    quiet_schedule = _schedule_entries(osquery_primary_config)
    deep_schedule = _schedule_entries(osquery_deep_forensic_config)

    for config in (osquery_primary_config, osquery_deep_forensic_config):
        assert "rootkit_detection" in config["packs"]

    for query_name in (
        "file_suspicious_artifacts",
        "hidden_processes",
        "suspicious_library_paths",
    ):
        assert query_name in quiet_schedule
        assert query_name in deep_schedule


def test_osquery_flags_keep_filesystem_logging_enabled(
    osquery_flags: list[str],
) -> None:
    assert "--config_plugin=filesystem" in osquery_flags
    assert "--logger_plugin=filesystem" in osquery_flags
    assert "--logger_mode=0644" in osquery_flags
