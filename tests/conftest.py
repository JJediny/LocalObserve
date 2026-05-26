from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-stack",
        action="store_true",
        default=False,
        help="Run live-stack integration tests that require Docker services.",
    )
    parser.addoption(
        "--run-host-emulation",
        action="store_true",
        default=False,
        help="Run host-side emulation tests that execute CALDERA abilities locally.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: tests that exercise the running OpenObserve/Falco stack",
    )
    config.addinivalue_line(
        "markers",
        "host_emulation: tests that execute host-side emulation commands and emit OTEL traces",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    skip_integration = pytest.mark.skip(
        reason="need --run-stack to run live stack integration tests",
    )
    skip_host_emulation = pytest.mark.skip(
        reason="need --run-host-emulation to run host-side emulation tests",
    )
    for item in items:
        if "integration" in item.keywords and not config.getoption("--run-stack"):
            item.add_marker(skip_integration)
        if "host_emulation" in item.keywords and not config.getoption("--run-host-emulation"):
            item.add_marker(skip_host_emulation)


def _read_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _load_json(relative_path: str) -> dict:
    return json.loads(_read_text(relative_path))


def _load_yaml(relative_path: str):
    return yaml.safe_load(_read_text(relative_path))


def _load_flag_lines(relative_path: str) -> list[str]:
    return [
        line.strip()
        for line in _read_text(relative_path).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def falco_config() -> dict:
    return _load_yaml("falco-config.yaml")


@pytest.fixture(scope="session")
def falco_rules() -> list[dict]:
    return _load_yaml("falco_rules.local.yaml")


@pytest.fixture(scope="session")
def osquery_primary_config() -> dict:
    return _load_json("osqueryd.conf")


@pytest.fixture(scope="session")
def osquery_deep_forensic_config() -> dict:
    return _load_json("osqueryd-deep-forensic.conf")


@pytest.fixture(scope="session")
def osquery_ssd_config() -> dict:
    return _load_json("osqueryd-ssd-optimized.conf")


@pytest.fixture(scope="session")
def osquery_flags() -> list[str]:
    return _load_flag_lines("osquery.flags")
