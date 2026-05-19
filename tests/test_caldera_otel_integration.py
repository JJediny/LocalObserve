from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


pytestmark = [pytest.mark.integration, pytest.mark.host_emulation]

SAFE_LIST_DIRECTORY_ABILITY = "52177cc1-b9ab-4411-ac21-2eadc4b5d3b8"
SAFE_WIFI_ABILITY = "a0676fe1-cd52-482e-8dde-349b73f9aa69"


def _run(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_caldera_ability_emits_trace_to_openobserve(repo_root: Path) -> None:
    result = _run(
        repo_root,
        [
            "uv",
            "run",
            "python",
            "tools/caldera_otel_harness.py",
            "run-ability",
            "--bootstrap",
            "--ability-id",
            SAFE_LIST_DIRECTORY_ABILITY,
            "--verify-trace",
        ],
    )

    payload = json.loads(result.stdout)
    assert payload["ability_id"] == SAFE_LIST_DIRECTORY_ABILITY
    assert payload["exit_code"] == 0
    assert payload["trace"]["verified"] is True
    assert payload["trace"]["hits"], "expected emitted span to be searchable in OpenObserve"
    first_hit = payload["trace"]["hits"][0]
    assert first_hit["service_name"] == "caldera-host-emulation"
    assert first_hit["operation_name"] == f"caldera.{SAFE_LIST_DIRECTORY_ABILITY}"


def test_caldera_lists_curated_safe_linux_abilities(repo_root: Path) -> None:
    result = _run(
        repo_root,
        [
            "uv",
            "run",
            "python",
            "tools/caldera_otel_harness.py",
            "list-safe-abilities",
        ],
    )

    payload = json.loads(result.stdout)
    ability_ids = {entry["ability_id"] for entry in payload}
    assert SAFE_LIST_DIRECTORY_ABILITY in ability_ids
    assert SAFE_WIFI_ABILITY in ability_ids

    wifi_entry = next(entry for entry in payload if entry["ability_id"] == SAFE_WIFI_ABILITY)
    assert wifi_entry["payloads"] == ["wifi.sh"]
