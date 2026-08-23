"""Contract tests for the repository's mise-managed developer toolchain."""
from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_python_and_security_toolchain_versions_are_pinned() -> None:
    with (REPO_ROOT / "mise.toml").open("rb") as handle:
        tools = tomllib.load(handle)["tools"]

    assert tools["uv"] == "0.12.5"
    assert tools["task"] == "3.53.1"
    assert tools["betterleaks"] == "1.8.1"
    assert tools["osv-scanner"] == "2.5.1"


def test_mise_toolchain_declares_all_runtime_clients() -> None:
    with (REPO_ROOT / "mise.toml").open("rb") as handle:
        tools = tomllib.load(handle)["tools"]

    for runtime in ("docker-cli", "podman", "nerdctl", "docker-compose"):
        assert runtime in tools


def test_mise_toolchain_declares_otelcol_contrib_validator() -> None:
    """otelcol-contrib is NOT pinned via mise because the UBI backend is
    unreliable across architectures (different archive layouts on CI vs
    local). The config validation test in test_otel_ottl.py skips
    gracefully when the binary is absent and runs when available."""
    with (REPO_ROOT / "mise.toml").open("rb") as handle:
        tools = tomllib.load(handle)["tools"]

    key = "ubi:open-telemetry/opentelemetry-collector-releases"
    assert key not in tools, (
        f"otelcol-contrib UBI pin was removed — UBI backend is unreliable in CI; "
        f"install otelcol-contrib manually if needed for binary config validation"
    )
