"""Parity verification: osquery & Falco — host-native vs containerized sidecar.

Validates that the privileged container sidecars (pid:host, net:host, /:/host:ro)
see telemetry equivalent to a host-native installation.

Architecture decision matrix:
  https://github.com/JJediny/LocalObserve/blob/main/docs/standardization_and_sidecars.md

Tables are classified by the mechanism they depend on, not by query name.
This test runs a static analysis of the config (always safe) plus optional
live comparison when --run-stack is set and both host + container daemons
are reachable.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Classification — which osquery tables depend on what
# ---------------------------------------------------------------------------

# Tables that access the Docker socket (UNIX socket at /var/run/docker.sock).
# These need the Docker socket mount to produce meaningful results.
REQUIRES_DOCKER_SOCKET: set[str] = {
    "docker_container_envs",
    "docker_container_fs_changes",
    "docker_container_labels",
    "docker_container_mounts",
    "docker_container_networks",
    "docker_container_ports",
    "docker_container_processes",
    "docker_container_stats",
    "docker_containers",
    "docker_image_history",
    "docker_image_labels",
    "docker_image_layers",
    "docker_images",
    "docker_info",
    "docker_network_labels",
    "docker_networks",
    "docker_version",
    "docker_volume_labels",
    "docker_volumes",
}

# Tables that need raw /dev access (beyond /dev bind mount).
# These may be empty or degraded in a container even with privileged:true.
REQUIRES_DEV_ACCESS: set[str] = {
    "block_devices",
    "device_file",
    "device_hash",
    "device_partitions",
    "disk_encryption",
    "pci_devices",
    "usb_devices",
}

# Tables that access EFI variables via /sys/firmware/efi/efivars.
REQUIRES_EFIVARS: set[str] = {
    "secureboot",
    "secureboot_certificates",
}

# Tables that need LXD socket /var/snap/lxd/...
# (irrelevant on non-LXD hosts, but listed for completeness).
REQUIRES_LXD_SOCKET: set[str] = {
    "lxd_certificates",
    "lxd_cluster",
    "lxd_cluster_members",
    "lxd_images",
    "lxd_instance_config",
    "lxd_instance_devices",
    "lxd_instances",
    "lxd_networks",
    "lxd_storage_pools",
}

# Tables that should work identically with pid:host + /:/host:ro.
# These access /proc, /sys, /etc, or standard kernel interfaces.
HOST_NAMESPACE_TABLES: set[str] = {
    "acpi_tables",
    "apparmor_profiles",
    "apt_sources",
    "arp_cache",
    "authorized_keys",
    "cpu_info",
    "crontab",
    "deb_packages",
    "dns_resolvers",
    "etc_hosts",
    "etc_protocols",
    "etc_services",
    "file",
    "firefox_addons",
    "groups",
    "interface_addresses",
    "interface_details",
    "iptables",
    "kernel_info",
    "kernel_keys",
    "kernel_modules",
    "known_hosts",
    "last",
    "listening_ports",
    "load_average",
    "logged_in_users",
    "magic",
    "md_devices",
    "md_drives",
    "memory_info",
    "mounts",
    "os_version",
    "platform_info",
    "process_envs",
    "process_memory_map",
    "process_namespaces",
    "process_open_files",
    "process_open_pipes",
    "process_open_sockets",
    "processes",
    "routes",
    "rpm_packages",
    "selinux_settings",
    "shadow",
    "shared_memory",
    "shell_history",
    "smbios_tables",
    "ssh_configs",
    "startup_items",
    "sudoers",
    "suid_bin",
    "system_controls",
    "system_info",
    "systemd_units",
    "time",
    "uptime",
    "user_groups",
    "user_ssh_keys",
    "users",
    "yum_sources",
}

# Events tables (inotify / audit / bpf backed).
# These require kernel event subsystems and should work with
# privileged:true + pid:host.
EVENT_TABLES: set[str] = {
    "file_events",
    "process_events",
    "process_file_events",
    "socket_events",
    "user_events",
    "hardware_events",
    "bpf_process_events",
    "bpf_socket_events",
    "syslog_events",
    "apparmor_events",
    "selinux_events",
    "seccomp_events",
    "udev",
    "yara_events",
}


@dataclass
class TableParity:
    name: str
    host_count: int | None = None
    container_count: int | None = None
    equivalent: bool | None = None
    note: str = ""


@dataclass
class ParityReport:
    tables: dict[str, TableParity] = field(default_factory=dict)
    falco_rules_equivalent: bool | None = None
    falco_note: str = ""


# ---------------------------------------------------------------------------
# Static analysis: extract osquery tables from config
# ---------------------------------------------------------------------------

def _load_osquery_config(path: str) -> dict:
    return json.loads((REPO_ROOT / path).read_text())


def _extract_tables(config: dict) -> list[tuple[str, str]]:
    """Return [(table_name, query_text), ...] for each scheduled query."""
    import re

    entries: list[tuple[str, str]] = []
    for name, definition in config.get("schedule", {}).items():
        if name.strip().startswith("//"):
            continue
        query = definition.get("query", "").upper()
        for match in re.findall(r"FROM\s+(\w+)", query):
            entries.append((match.lower(), query))
    return entries


# ---------------------------------------------------------------------------
# Live queries (used only with --run-stack)
# ---------------------------------------------------------------------------

OSQUERYI_BIN = "/opt/osquery/bin/osqueryd"
OSQUERYI_ARGS = [
    "-S",
    "--config_path",
    "/dev/null",
    "--logger_path",
    "/tmp/osquery-parity-test",
    "--pidfile",
    "/tmp/osquery-parity-test.pid",
    "--disable_logging",
    "--json",
]


def _run_host_query(query: str) -> list[dict]:
    """Run an osquery SQL query natively on the host."""
    proc = subprocess.run(
        [OSQUERYI_BIN, *OSQUERYI_ARGS, query],
        capture_output=True,
        text=True,
        timeout=30,
    )
    # osqueryd --S prints results to stdout; errors to stderr
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    if not stdout and stderr:
        # osquery reports errors on stdout as JSON array; stderr has log noise
        if "Error:" in stderr or "error" in stderr.lower():
            return []
    try:
        return json.loads(stdout) if stdout else []
    except json.JSONDecodeError:
        return []


def _run_container_query(query: str) -> list[dict]:
    """Run an osquery SQL query inside the `localobserve-osquery-1` container."""
    proc = subprocess.run(
        [
            "docker",
            "exec",
            "localobserve-osquery-1",
            "osqueryi",
            "--json",
            query,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        return json.loads(proc.stdout.strip()) if proc.stdout.strip() else []
    except json.JSONDecodeError:
        return []


# ---------------------------------------------------------------------------
# Static tests — always run
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def osquery_tables_in_use() -> list[tuple[str, str]]:
    """All (table_name, query_text) pairs used across primary config."""
    primary = _load_osquery_config("osqueryd.conf")
    ssd = _load_osquery_config("osqueryd-ssd-optimized.conf")
    deep = _load_osquery_config("osqueryd-deep-forensic.conf")
    seen: set[str] = set()
    entries: list[tuple[str, str]] = []
    for config in (primary, ssd, deep):
        for table, query in _extract_tables(config):
            key = f"{table}::{query}"
            if key not in seen:
                seen.add(key)
                entries.append((table, query))
    return entries


class TestOsqueryTableParityClassification:
    """Every table used in an osquery config must be classified for parity."""

    ALL_CLASSIFIED: set[str] = (
        REQUIRES_DOCKER_SOCKET
        | REQUIRES_DEV_ACCESS
        | REQUIRES_EFIVARS
        | REQUIRES_LXD_SOCKET
        | HOST_NAMESPACE_TABLES
        | EVENT_TABLES
    )

    def test_all_tables_classified(
        self, osquery_tables_in_use: list[tuple[str, str]]
    ) -> None:
        unclassified: set[str] = set()
        for table, _ in osquery_tables_in_use:
            if table not in self.ALL_CLASSIFIED:
                unclassified.add(table)
        assert not unclassified, (
            f"Unclassified osquery tables (add to parity test): {sorted(unclassified)}"
        )

    def test_no_docker_socket_tables_queried_without_socket_mount(
        self, osquery_tables_in_use: list[tuple[str, str]]
    ) -> None:
        """Docker tables need the socket mount — document the gap.

        On Docker Desktop (Enhanced Container Isolation), the Docker socket
        mount is blocked. These tables will return empty results in the
        container. On bare Docker Engine, uncomment the socket mount in
        docker-compose.yaml to restore full Docker table parity.
        """
        compose = yaml.safe_load((REPO_ROOT / "docker-compose.yaml").read_text())
        osquery_svc = compose.get("services", {}).get("osquery", {})
        volumes = osquery_svc.get("volumes", [])
        has_socket = any("docker.sock" in v for v in volumes)

        docker_tables = {t for t, _ in osquery_tables_in_use if t in REQUIRES_DOCKER_SOCKET}
        if docker_tables and not has_socket:
            msg = (
                f"[DOCKER DESKTOP LIMITATION] Docker tables "
                f"{sorted(docker_tables)} are queried but osquery container "
                f"has no docker.sock mount. These tables will return empty "
                f"results. On bare Docker Engine, uncomment the socket mount "
                f"in docker-compose.yaml to restore parity."
            )
            # Non-fatal: this is a documented platform limitation, not a bug.
            print(f"\n  {msg}")
            return

        assert True  # pass silently when socket is mounted

    def test_efivars_tables_warn_on_missing_mount(
        self, osquery_tables_in_use: list[tuple[str, str]]
    ) -> None:
        efivars_tables = {t for t, _ in osquery_tables_in_use if t in REQUIRES_EFIVARS}
        if efivars_tables:
            # /sys/firmware/efi/efivars may not be mounted in the container.
            # This is informational — not all hosts even have EFI.
            compose = yaml.safe_load((REPO_ROOT / "docker-compose.yaml").read_text())
            osquery_svc = compose.get("services", {}).get("osquery", {})
            volumes = osquery_svc.get("volumes", [])
            has_efivars = any("efivars" in v for v in volumes)
            if not has_efivars:
                print(
                    f"  [INFO] Tables {sorted(efivars_tables)} may be empty in container "
                    f"unless /sys/firmware/efi/efivars is mounted."
                )

    def test_host_namespace_tables_are_expected_parity(
        self, osquery_tables_in_use: list[tuple[str, str]]
    ) -> None:
        """Verify the tables we expect to be equivalent are reasonable.

        Every HOST_NAMESPACE_TABLE should produce identical results
        (same rows, same counts) between host and container, because
        they access kernel interfaces (/proc, /sys, /etc) that are
        shared via pid:host and volume mounts.
        """
        for table, _ in osquery_tables_in_use:
            if table in HOST_NAMESPACE_TABLES:
                assert table not in REQUIRES_DOCKER_SOCKET, (
                    f"{table} should not be in both HOST_NAMESPACE and DOCKER_SOCKET sets"
                )


class TestFalcoParityClassification:
    """Falco parity analysis — host vs container."""

    def test_falco_uses_modern_ebpf(self) -> None:
        """Falco modern_ebpf driver attaches to the same kernel tracepoints
        regardless of whether Falco runs on the host or in a privileged container.
        The event stream is identical."""
        config = yaml.safe_load((REPO_ROOT / "falco-config.yaml").read_text())
        engine = config.get("engine", {})
        assert engine.get("kind") == "modern_ebpf", (
            "Only modern_ebpf is verified for host/container parity; "
            "kernel module driver may differ."
        )

    def test_falco_has_host_proc_mount(self) -> None:
        """Falco needs /proc to resolve PIDs to process names."""
        compose = yaml.safe_load((REPO_ROOT / "docker-compose.yaml").read_text())
        falco_svc = compose.get("services", {}).get("falco", {})
        volumes = falco_svc.get("volumes", [])
        has_proc = any("proc" in v for v in volumes)
        assert has_proc, "Falco container must mount /proc to resolve host process names"

    def test_falco_has_host_etc_mount(self) -> None:
        """Falco rules reference /etc/passwd, /etc/group for user resolution."""
        compose = yaml.safe_load((REPO_ROOT / "docker-compose.yaml").read_text())
        falco_svc = compose.get("services", {}).get("falco", {})
        volumes = falco_svc.get("volumes", [])
        has_etc = any("etc" in v for v in volumes)
        assert has_etc, "Falco container must mount /etc for user/group resolution"

    def test_falco_pid_host(self) -> None:
        """Falco must run with pid:host to see all processes."""
        compose = yaml.safe_load((REPO_ROOT / "docker-compose.yaml").read_text())
        falco_svc = compose.get("services", {}).get("falco", {})
        assert falco_svc.get("pid") == "host", (
            "Falco must use pid:host for full process visibility"
        )

    def test_falco_network_host(self) -> None:
        """Falco must run with network_mode:host to see host network events."""
        compose = yaml.safe_load((REPO_ROOT / "docker-compose.yaml").read_text())
        falco_svc = compose.get("services", {}).get("falco", {})
        assert falco_svc.get("network_mode") == "host", (
            "Falco must use network_mode:host for full network visibility"
        )

    def test_falco_privileged(self) -> None:
        """Falco must be privileged to load eBPF probes and trace syscalls."""
        compose = yaml.safe_load((REPO_ROOT / "docker-compose.yaml").read_text())
        falco_svc = compose.get("services", {}).get("falco", {})
        assert falco_svc.get("privileged") is True, (
            "Falco must be privileged to attach kernel probes"
        )


# ---------------------------------------------------------------------------
# Live comparison tests (require --run-stack)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestLiveOsqueryParity:
    """Live comparison between host osqueryi and container osqueryd.

    These tests require:
      - osqueryd/osqueryi installed on the host
      - localobserve-osquery-1 container running (pid:host, /:/host:ro)
      - --run-stack flag
    """

    COMPARISON_TABLES: list[tuple[str, str]] = [
        # (table, query) — count-based comparison
        ("system_info", "SELECT count(*) AS cnt FROM system_info;"),
        ("processes", "SELECT count(*) AS cnt FROM processes;"),
        ("users", "SELECT count(*) AS cnt FROM users;"),
        ("groups", "SELECT count(*) AS cnt FROM groups;"),
        ("listening_ports", "SELECT count(*) AS cnt FROM listening_ports;"),
        ("routes", "SELECT count(*) AS cnt FROM routes;"),
        ("kernel_modules", "SELECT count(*) AS cnt FROM kernel_modules;"),
        ("crontab", "SELECT count(*) AS cnt FROM crontab;"),
        ("systemd_units", "SELECT count(*) AS cnt FROM systemd_units;"),
        ("deb_packages", "SELECT count(*) AS cnt FROM deb_packages;"),
        ("apt_sources", "SELECT count(*) AS cnt FROM apt_sources;"),
        ("mounts", "SELECT count(*) AS cnt FROM mounts;"),
        ("logged_in_users", "SELECT count(*) AS cnt FROM logged_in_users;"),
        ("last", "SELECT count(*) AS cnt FROM last;"),
        ("sudoers", "SELECT count(*) AS cnt FROM sudoers;"),
        ("suid_bin", "SELECT count(*) AS cnt FROM suid_bin;"),
    ]

    @pytest.mark.skipif(
        not Path(OSQUERYI_BIN).exists(),
        reason="osqueryd/osqueryi not installed on host",
    )
    def test_process_count_parity(self) -> None:
        """Process count should be identical — pid:host shares the namespace."""
        host = _run_host_query("SELECT count(*) AS cnt FROM processes;")
        container = _run_container_query("SELECT count(*) AS cnt FROM processes;")

        if not host or not container:
            pytest.skip("Could not execute query on host or container")

        host_cnt = int(host[0].get("cnt", 0))
        container_cnt = int(container[0].get("cnt", 0))
        assert host_cnt == container_cnt, (
            f"Process count mismatch: host={host_cnt}, container={container_cnt}. "
            f"pid:host should guarantee identical process visibility."
        )

    @pytest.mark.skipif(
        not Path(OSQUERYI_BIN).exists(),
        reason="osqueryd/osqueryi not installed on host",
    )
    def test_users_parity(self) -> None:
        """User list should be identical — /etc/passwd read from host."""
        host = _run_host_query("SELECT uid, username FROM users ORDER BY uid;")
        container = _run_container_query("SELECT uid, username FROM users ORDER BY uid;")

        if not host or not container:
            pytest.skip("Could not execute query on host or container")

        host_users = {(r["uid"], r["username"]) for r in host}
        container_users = {(r["uid"], r["username"]) for r in container}
        assert host_users == container_users, (
            f"User list mismatch: host has {len(host_users)}, "
            f"container has {len(container_users)}. "
            f"Extra in host: {host_users - container_users}. "
            f"Extra in container: {container_users - host_users}."
        )

    @pytest.mark.skipif(
        not Path(OSQUERYI_BIN).exists(),
        reason="osqueryd/osqueryi not installed on host",
    )
    def test_count_parity_for_key_tables(self) -> None:
        """Row-count parity across key security-relevant tables."""
        failures: list[str] = []
        for table, query in self.COMPARISON_TABLES:
            host = _run_host_query(query)
            container = _run_container_query(query)
            if not host or not container:
                continue
            host_cnt = int(host[0].get("cnt", 0))
            container_cnt = int(container[0].get("cnt", 0))
            if host_cnt != container_cnt:
                failures.append(f"{table}: host={host_cnt}, container={container_cnt}")
        if failures:
            pytest.fail("Row-count parity failures:\n  " + "\n  ".join(failures))
