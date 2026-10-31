from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_openobserve_uses_runtime_managed_named_volume() -> None:
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yaml").read_text())

    assert compose["services"]["openobserve"]["volumes"] == ["openobserve_data:/data"]
    assert compose["volumes"]["openobserve_data"] == {
        "external": True,
        "name": "localobserve_openobserve_data",
    }
    assert "./.data/openobserve-data:/data" not in (REPO_ROOT / "docker-compose.yaml").read_text()


def test_rootless_podman_data_migration_is_scripted() -> None:
    migration_script = REPO_ROOT / "scripts" / "migrate-openobserve-data.sh"

    assert migration_script.exists()
    assert migration_script.stat().st_mode & 0o111
    script = migration_script.read_text()
    assert "_openobserve_data" in script
    assert "$BINARY stop" in script
    assert 'volume create "$DEST_VOLUME"' in script
    assert 'localobserve_openobserve_data' in script


def test_mise_exposes_storage_migration_tasks() -> None:
    with (REPO_ROOT / "mise.toml").open("rb") as handle:
        tasks = tomllib.load(handle)["tasks"]

    assert "storage:migrate" in tasks
    assert "storage:migrate:podman" in tasks
