"""Tests for tools/sync_threat_intel.py (offline, mocked network)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

# Load the script as a module without polluting the package namespace.
_spec = importlib.util.spec_from_file_location(
    "sync_threat_intel", REPO_ROOT / "tools" / "sync_threat_intel.py"
)
sync = importlib.util.module_from_spec(_spec)
sys.modules["sync_threat_intel"] = sync
_spec.loader.exec_module(sync)

SAMPLE = {
    # _fake_fetch stands in for sync.fetch, which already returns cleaned lines.
    "tor_ips": ["1.2.3.4", "5.6.7.8"],
    "vpn_ips": ["9.9.9.9", "2001:db8::1"],
    "bad_user_agents": ["BadBot/1.0", "curl/xyz"],
    "named_pipes": [r"\\Device\\NamedPipe\\foo", "spoolss"],
    "ransomware_extensions": [".Locky", "Crypt", ".zepto", "LOCKY"],
}


def _fake_fetch(url: str, timeout: int = 20) -> list[str]:
    for key, rel in sync.DEFAULT_SOURCES.items():
        if rel in url:
            return SAMPLE[key]
    return []


def test_sync_writes_clean_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "fetch", _fake_fetch)
    sync.run(["--output-dir", str(tmp_path), "--mount-dir", "/var/lib/threat-intel"])

    # Comments and blank lines are stripped.
    assert (tmp_path / "tor_ips.txt").read_text().split() == ["1.2.3.4", "5.6.7.8"]
    # Extension normalization lowercases, strips leading dots, sorts, and dedupes.
    assert (tmp_path / "ransomware_extensions.txt").read_text().split() == [
        "crypt",
        "locky",
        "zepto",
    ]
    assert (tmp_path / "threat_intel.json").exists()
    assert (tmp_path / "osquery.threat_intel.conf").exists()


def test_verified_upstream_source_urls_are_stable():
    urls = sync.build_source_urls(sync.DEFAULT_BASE, {})
    assert urls["tor_ips"].endswith("Lists/TOR/only_tor_exit_nodes_IP_list.csv")
    assert urls["vpn_ips"] == (
        "https://github.com/mthcht/awesome-lists/releases/download/"
        "big-files/VPN_ALL_IP_List.csv"
    )
    assert urls["bad_user_agents"].endswith(
        "Lists/suspicious_http_user_agents_list.csv"
    )
    assert urls["named_pipes"].endswith("Lists/suspicious_named_pipe_list.csv")
    assert urls["ransomware_extensions"].endswith(
        "Lists/ransomware_extensions_list.csv"
    )


def test_csv_sources_extract_indicator_columns(tmp_path, monkeypatch):
    csv_sources = {
        "tor_ips": ["dest_ip", "1.2.3.4", "1.2.3.4"],
        "vpn_ips": [
            "src_ip,src_ip_entry,src_ip_exit",
            "1.1.1.1,2.2.2.2,2001:db8::1",
        ],
        "bad_user_agents": [
            "http_user_agent,metadata_comment",
            '"BadBot/1.0",example',
        ],
        "named_pipes": [
            "pipe_name,metadata_description",
            r"\\RoguePlanet,example",
        ],
        "ransomware_extensions": [
            "file_path,metadata_comment",
            "*.Locky,example",
        ],
    }

    def _fake_csv_fetch(url: str, timeout: int = 20) -> list[str]:
        for key, rel in sync.DEFAULT_SOURCES.items():
            if rel in url:
                return csv_sources[key]
        return []

    monkeypatch.setattr(sync, "fetch", _fake_csv_fetch)
    sync.run(["--output-dir", str(tmp_path)])

    assert (tmp_path / "tor_ips.txt").read_text().split() == ["1.2.3.4"]
    assert (tmp_path / "vpn_ips.txt").read_text().split() == [
        "1.1.1.1",
        "2.2.2.2",
        "2001:db8::1",
    ]
    assert (tmp_path / "bad_user_agents.txt").read_text().split() == ["BadBot/1.0"]
    assert (tmp_path / "named_pipes.txt").read_text().split() == [r"\\RoguePlanet"]
    assert (tmp_path / "ransomware_extensions.txt").read_text().split() == ["locky"]


def test_generated_falco_fragment_is_valid(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "fetch", _fake_fetch)
    sync.run(["--output-dir", str(tmp_path)])

    fragment = yaml.safe_load(
        (tmp_path / "falco_rules.threat_intel.local.yaml").read_text()
    )
    assert isinstance(fragment, list)
    names = {entry["list"] for entry in fragment}
    assert names == set(sync.KEY_TO_FALCO_LIST.values())
    bad_uas = next(
        e for e in fragment if e["list"] == "threat_intel_bad_user_agents"
    )
    assert bad_uas["items"] == ["BadBot/1.0", "curl/xyz"]
    assert bad_uas["override"] == {"items": "append"}


def test_offline_reuses_cache(tmp_path, monkeypatch):
    # First run populates the cache.
    monkeypatch.setattr(sync, "fetch", _fake_fetch)
    sync.run(["--output-dir", str(tmp_path)])
    assert (tmp_path / "tor_ips.cache").exists()

    # Second run: network is down, must fall back to cache (no crash, data kept).
    def _boom(url, timeout=20):
        raise RuntimeError("offline")

    monkeypatch.setattr(sync, "fetch", _boom)
    sync.run(["--output-dir", str(tmp_path)])
    assert (tmp_path / "tor_ips.txt").read_text().split() == ["1.2.3.4", "5.6.7.8"]


def test_no_cache_writes_valid_stubs(tmp_path, monkeypatch):
    def _boom(url, timeout=20):
        raise RuntimeError("offline")

    monkeypatch.setattr(sync, "fetch", _boom)
    # No cache present -> still writes valid (empty) artifacts and exits 0.
    assert (
        sync.run(["--output-dir", str(tmp_path), "--no-cache"]) == 0
    )
    fragment = yaml.safe_load(
        (tmp_path / "falco_rules.threat_intel.local.yaml").read_text()
    )
    assert all(entry["items"] == [] for entry in fragment)


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "fetch", _fake_fetch)
    assert sync.run(["--output-dir", str(tmp_path), "--dry-run"]) == 0
    assert not (tmp_path / "tor_ips.txt").exists()


# --- Integration contract: the repo configs must wire the generated feeds ---


def test_osquery_file_paths_includes_threat_intel():
    cfg = json.loads((REPO_ROOT / "osqueryd.conf").read_text())
    assert "threat_intel" in cfg["file_paths"]
    assert any(
        "threat-intel" in p for p in cfg["file_paths"]["threat_intel"]
    )
    assert "/var/lib/threat-intel/vpn_ips.txt" in cfg["file_paths"]["threat_intel"]


def test_falco_config_loads_threat_intel_fragment():
    cfg = yaml.safe_load((REPO_ROOT / "falco-config.yaml").read_text())
    assert "/var/lib/threat-intel/falco_rules.threat_intel.local.yaml" in cfg.get(
        "rules_files", []
    )


def test_compose_mounts_threat_intel_into_all_consumers():
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yaml").read_text())
    for service_name in ("falco", "osquery", "otel-collector"):
        volumes = compose["services"][service_name].get("volumes", [])
        assert any(".data/threat-intel:/var/lib/threat-intel" in v for v in volumes)
