from __future__ import annotations

import base64
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
import warnings
from pathlib import Path

import pytest

LOKI_QUERY_URL = "http://localhost:3100/loki/api/v1/query_range"
LOKI_TENANT = "tenant1"
OPENOBSERVE_STREAMS_URL = "http://localhost:5080/api/default/streams"
FALCO_FILE_PATH = Path(".data/falco/events.jsonl")

_OPENOBSERVE_USERNAME = os.environ.get("OPENOBSERVE_USERNAME")
_OPENOBSERVE_PASSWORD = os.environ.get("OPENOBSERVE_PASSWORD")
OPENOBSERVE_AUTH = (_OPENOBSERVE_USERNAME or "", _OPENOBSERVE_PASSWORD or "")

pytestmark = pytest.mark.integration


def _run(
    repo_root: Path,
    args: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=repo_root,
        check=check,
        capture_output=True,
        text=True,
    )


def _get_json(url: str, *, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def _openobserve_streams() -> dict:
    token = base64.b64encode(
        f"{OPENOBSERVE_AUTH[0]}:{OPENOBSERVE_AUTH[1]}".encode("utf-8")
    ).decode("ascii")
    return _get_json(
        OPENOBSERVE_STREAMS_URL,
        headers={"Authorization": f"Basic {token}"},
    )


def _openobserve_doc_count(stream_name: str) -> int:
    streams = _openobserve_streams()["list"]
    for stream in streams:
        if stream["name"] == stream_name:
            return int(stream["stats"]["doc_num"])
    return 0


def _loki_query(query: str, *, limit: int = 5) -> dict:
    params = urllib.parse.urlencode({"query": query, "limit": str(limit)})
    return _get_json(
        f"{LOKI_QUERY_URL}?{params}",
        headers={"X-Scope-OrgID": LOKI_TENANT},
    )


def _wait_for(predicate, *, timeout: int = 45, interval: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError("condition was not met before timeout")


def _emit_synthetic_falco_event(repo_root: Path, rule_name: str, marker: str) -> None:
    event_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 2))
    payload = json.dumps(
        {
            "output": marker,
            "priority": "Warning",
            "rule": rule_name,
            "time": event_time,
            "output_fields": {
                "proc.cmdline": marker,
                "user.name": "pytest",
            },
        }
    )
    _run(
        repo_root,
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "falcosidekick",
            "wget",
            "-qO-",
            "--header",
            "Content-Type: application/json",
            "--post-data",
            payload,
            "http://127.0.0.1:2801/",
        ],
    )


def _collector_logs(repo_root: Path) -> str:
    return _run(
        repo_root,
        ["docker", "compose", "logs", "--no-color", "otel-collector"],
    ).stdout


@pytest.mark.skip(reason="Loki not in current docker-compose stack — see docs/future_roadmap.md")
def test_loki_is_queryable() -> None:
    data = _loki_query('{job="osquery"}', limit=1)
    assert data["status"] == "success"


@pytest.mark.skip(reason="Loki not in current docker-compose stack — see docs/future_roadmap.md")
def test_osquery_logs_are_present_in_loki() -> None:
    data = _loki_query('{job="osquery"}', limit=1)
    assert data["data"]["result"], "expected at least one osquery stream in Loki"


@pytest.mark.skipif(
    not _OPENOBSERVE_USERNAME or not _OPENOBSERVE_PASSWORD,
    reason="OPENOBSERVE_USERNAME and OPENOBSERVE_PASSWORD environment variables are not set"
)
def test_osquery_stream_has_documents_in_openobserve() -> None:
    assert _openobserve_doc_count("osquery") > 0


@pytest.mark.skip(reason="Loki not in current docker-compose stack — see docs/future_roadmap.md")
def test_synthetic_falco_event_reaches_loki(repo_root: Path) -> None:
    rule_name = f"Pytest Synthetic Falco Rule {uuid.uuid4().hex[:8]}"
    marker = f"PYTEST_FALCO_{uuid.uuid4().hex[:12]}"

    _emit_synthetic_falco_event(repo_root, rule_name, marker)

    def _seen_in_loki() -> bool:
        data = _loki_query(f'{{rule="{rule_name}"}}', limit=5)
        return bool(data["data"]["result"])

    _wait_for(_seen_in_loki)


def test_otel_collector_watches_falco_file_when_present(repo_root: Path) -> None:
    FALCO_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FALCO_FILE_PATH.touch(exist_ok=True)

    _run(repo_root, ["docker", "compose", "restart", "otel-collector"])

    def _watching_file() -> bool:
        logs = _collector_logs(repo_root)
        return "Started watching file" in logs and "/var/log/falco/events.jsonl" in logs

    _wait_for(_watching_file)


def test_loki_metrics_no_rate_limiting() -> None:
    request = urllib.request.Request("http://localhost:3100/metrics")
    with urllib.request.urlopen(request, timeout=20) as response:
        metrics = response.read().decode("utf-8")
        
    for line in metrics.splitlines():
        if "loki_distributor_discarded_samples_total" in line and 'reason="rate_limited"' in line:
            count = float(line.split()[-1])
            assert count == 0.0, f"Rate limiting detected in Loki metrics: {line}"
