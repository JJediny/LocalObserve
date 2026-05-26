"""caldera_otel_harness: run CALDERA stockpile abilities on a live Linux host,
emit OpenTelemetry traces, and optionally correlate Falco/osquery log events via
OpenObserve.  NOTE: Linux-only; Windows/macOS support is a planned future feature.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

import yaml
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CALDERA_DIR = REPO_ROOT / ".data" / "caldera"
DEFAULT_ABILITY_ID = "52177cc1-b9ab-4411-ac21-2eadc4b5d3b8"
DEFAULT_TRACE_SERVICE = "caldera-host-emulation"
DEFAULT_TRACE_ENDPOINT = "http://localhost:4318/v1/traces"
DEFAULT_TRACE_SEARCH_URL = "http://localhost:5080/api/default/_search?type=traces"
DEFAULT_LOG_SEARCH_URL = "http://localhost:5080/api/default/_search"
DEFAULT_TRACE_LOOKBACK_SECONDS = 900
DEFAULT_TRACE_VERIFY_TIMEOUT_SECONDS = 20
DEFAULT_TRACE_VERIFY_INTERVAL_SECONDS = 2
DEFAULT_LOG_LOOKBACK_SECONDS = 120
DEFAULT_LOG_VERIFY_TIMEOUT_SECONDS = 20
DEFAULT_LOG_VERIFY_INTERVAL_SECONDS = 2
PLACEHOLDER_PATTERN = re.compile(r"#\{([^}]+)\}")
DUMP_HISTORY_ABILITY_ID = "422526ec-27e9-429a-995b-c686a29561a4"
AVOID_LOGS_ABILITY_ID = "43b3754c-def4-4699-a673-1d85648fda6a"
PAYLOAD_WIFI_ABILITY_ID = "a0676fe1-cd52-482e-8dde-349b73f9aa69"
SAFE_LINUX_ABILITIES: dict[str, str] = {
    "52177cc1-b9ab-4411-ac21-2eadc4b5d3b8": "List Directory",
    "6e1a53c0-7352-4899-be35-fa7f364d5722": "Print Working Directory",
    "335cea7b-bec0-48c6-adfb-6066070f5f68": "View Processes",
    "5a39d7ed-45c9-4a79-b581-e5fb99e24f65": "System processes",
    "5c4dd985-89e3-4590-9b57-71fed66ff4e2": "Permission Groups Discovery",
    PAYLOAD_WIFI_ABILITY_ID: "Preferred WIFI",
    DUMP_HISTORY_ABILITY_ID: "Dump history",
    AVOID_LOGS_ABILITY_ID: "Avoid logs",
}


@dataclass(slots=True)
class Ability:
    ability_id: str
    name: str
    description: str
    tactic: str
    technique_id: str
    technique_name: str
    executor: str
    command: str
    cleanup: str | None
    payloads: list[str]
    source_path: Path


@dataclass(slots=True)
class StagedAbility:
    command: str
    cleanup: str | None
    execution_dir: Path
    payload_paths: list[str]
    env: dict[str, str]
    artifacts: dict[str, Any]


@dataclass(slots=True)
class CorrelationQuery:
    stream: str
    sql: str
    expected: bool = True


@dataclass(slots=True)
class CorrelationExpectation:
    stream: str
    expected: bool
    reason: str


def _run_command(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def bootstrap_caldera_repo(caldera_dir: Path) -> None:
    caldera_dir.parent.mkdir(parents=True, exist_ok=True)
    if not caldera_dir.exists():
        _run_command(["git", "clone", "--depth", "1", "https://github.com/mitre/caldera", str(caldera_dir)])

    stockpile_dir = caldera_dir / "plugins" / "stockpile"
    if not stockpile_dir.exists() or not any(stockpile_dir.iterdir()):
        _run_command(
            [
                "git",
                "-C",
                str(caldera_dir),
                "submodule",
                "update",
                "--init",
                "--depth",
                "1",
                "plugins/stockpile",
            ]
        )


def _ability_files(caldera_dir: Path) -> list[Path]:
    base = caldera_dir / "plugins" / "stockpile" / "data" / "abilities"
    return sorted(base.rglob("*.yml"))


def _load_yaml_entries(file_path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [entry for entry in data if isinstance(entry, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _resolve_platform_executor(
    entry: dict[str, Any],
    platform: str,
    executor: str,
) -> tuple[str, str | None, list[str]]:
    platforms = entry.get("platforms", {})
    platform_block = platforms.get(platform, {})
    executor_block = platform_block.get(executor, {})
    if not executor_block:
        raise ValueError(
            f"ability {entry.get('id')} does not define platform={platform!r} executor={executor!r}"
        )
    command = (executor_block.get("command") or "").strip()
    cleanup = executor_block.get("cleanup")
    if cleanup is not None:
        cleanup = cleanup.strip()
    if not command:
        raise ValueError(f"ability {entry.get('id')} has no runnable command")
    payloads = [str(payload) for payload in (executor_block.get("payloads") or [])]
    return command, cleanup, payloads


def load_ability(caldera_dir: Path, ability_id: str, *, platform: str, executor: str) -> Ability:
    for file_path in _ability_files(caldera_dir):
        for entry in _load_yaml_entries(file_path):
            if entry.get("id") != ability_id:
                continue
            command, cleanup, payloads = _resolve_platform_executor(entry, platform, executor)
            technique = entry.get("technique") or {}
            return Ability(
                ability_id=ability_id,
                name=str(entry.get("name", ability_id)),
                description=str(entry.get("description", "")),
                tactic=str(entry.get("tactic", "unknown")),
                technique_id=str(technique.get("attack_id", "")),
                technique_name=str(technique.get("name", "")),
                executor=executor,
                command=command,
                cleanup=cleanup,
                payloads=payloads,
                source_path=file_path,
            )
    raise FileNotFoundError(f"Unable to locate CALDERA ability {ability_id}")


def list_safe_linux_abilities(caldera_dir: Path, *, executor: str = "sh") -> list[Ability]:
    return [
        load_ability(caldera_dir, ability_id, platform="linux", executor=executor)
        for ability_id in SAFE_LINUX_ABILITIES
    ]


def _substitute_placeholders(command: str, facts: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in facts:
            raise ValueError(f"command requires fact {key!r}; provide it with --fact {key}=value")
        return facts[key]

    return PLACEHOLDER_PATTERN.sub(replace, command)


def _format_trace_id(value: int) -> str:
    return f"{value:032x}"


def _make_tracer(service_name: str, trace_endpoint: str):
    resource = Resource.create({"service.name": service_name})
    trace_provider = TracerProvider(resource=resource)
    trace_exporter = OTLPSpanExporter(endpoint=trace_endpoint)
    trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)
    return trace_provider, trace.get_tracer("localobserve.caldera_harness")


def _prepare_execution_shell(stage: StagedAbility, *, verify_logs: bool) -> str:
    if not verify_logs or not stage.payload_paths:
        return "/bin/sh"

    temp_shell = stage.execution_dir / "runner-sh"
    shutil.copy2("/bin/sh", temp_shell)
    temp_shell.chmod(temp_shell.stat().st_mode | 0o111)
    return str(temp_shell)


def _openobserve_request(
    url: str,
    *,
    username: str,
    password: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=20) as response:
        return json.load(response)


def _search_trace(
    trace_id: str,
    *,
    search_url: str,
    username: str,
    password: str,
    lookback_seconds: int,
) -> dict[str, Any]:
    end_time = int(time.time() * 1_000_000)
    start_time = end_time - lookback_seconds * 1_000_000
    sql = (
        "SELECT service_name, operation_name, trace_id, span_id, start_time, end_time "
        f'FROM "default" WHERE trace_id = \'{trace_id}\' ORDER BY _timestamp DESC LIMIT 5'
    )
    payload = {
        "query": {
            "sql": sql,
            "start_time": start_time,
            "end_time": end_time,
        },
        "regions": ["local"],
    }
    return _openobserve_request(
        search_url,
        username=username,
        password=password,
        payload=payload,
    )


def _wait_for_trace(
    trace_id: str,
    *,
    search_url: str,
    username: str,
    password: str,
    lookback_seconds: int,
    timeout_seconds: int,
    interval_seconds: int,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    latest: dict[str, Any] = {"hits": []}
    while time.time() < deadline:
        latest = _search_trace(
            trace_id,
            search_url=search_url,
            username=username,
            password=password,
            lookback_seconds=lookback_seconds,
        )
        if latest.get("hits"):
            return latest
        time.sleep(interval_seconds)
    return latest


def _search_logs(
    query: CorrelationQuery,
    *,
    search_url: str,
    username: str,
    password: str,
    start_time: int,
    end_time: int,
) -> dict[str, Any]:
    payload = {
        "query": {
            "sql": query.sql,
            "start_time": start_time,
            "end_time": end_time,
        },
        "regions": ["local"],
    }
    try:
        return _openobserve_request(
            search_url,
            username=username,
            password=password,
            payload=payload,
        )
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        if exc.code == 400 and "Search stream not found" in details:
            return {"hits": [], "stream_not_found": True}
        raise


def _wait_for_logs(
    queries: list[CorrelationQuery],
    *,
    search_url: str,
    username: str,
    password: str,
    start_time: int,
    end_time: int,
    timeout_seconds: int,
    interval_seconds: int,
) -> dict[str, dict[str, Any]]:
    deadline = time.time() + timeout_seconds
    latest = {query.stream: {"hits": []} for query in queries}
    while time.time() < deadline:
        latest = {
            query.stream: _search_logs(
                query,
                search_url=search_url,
                username=username,
                password=password,
                start_time=start_time,
                end_time=end_time,
            )
            for query in queries
        }
        if any(response.get("hits") for response in latest.values()):
            return latest
        time.sleep(interval_seconds)
    return latest


def _ability_payload_source_dir(caldera_dir: Path) -> Path:
    return caldera_dir / "plugins" / "stockpile" / "payloads"


def _stage_dump_history_ability(ability: Ability, facts: dict[str, str]) -> StagedAbility:
    synthetic_home = Path(tempfile.mkdtemp(prefix="caldera-history-", dir="/tmp"))
    try:
        history_path = synthetic_home / ".bash_history"
        history_path.write_text("whoami\npwd\n", encoding="utf-8")
        return StagedAbility(
            command=_substitute_placeholders(ability.command, facts),
            cleanup=None,
            execution_dir=REPO_ROOT,
            payload_paths=[],
            env={"HOME": str(synthetic_home)},
            artifacts={
                "history_path": str(history_path),
                "synthetic_home": str(synthetic_home),
            },
        )
    except Exception:
        # Clean up the temp dir immediately if staging fails to avoid /tmp leaks.
        shutil.rmtree(synthetic_home, ignore_errors=True)
        raise


def _stage_avoid_logs_ability(ability: Ability, facts: dict[str, str]) -> StagedAbility:
    history_path = Path.home() / ".bash_history"
    backup_dir = Path(tempfile.mkdtemp(prefix="caldera-avoidlogs-", dir="/tmp"))
    backup_path = backup_dir / "bash_history.backup"
    history_exists = history_path.exists()
    if history_exists:
        shutil.copy2(history_path, backup_path)
    else:
        backup_path.write_text("", encoding="utf-8")
        history_path.touch()

    cleanup_command = (
        f"cp {shlex.quote(str(backup_path))} {shlex.quote(str(history_path))}"
        if history_exists
        else f"rm -f {shlex.quote(str(history_path))}"
    )
    return StagedAbility(
        command=_substitute_placeholders(ability.command, facts),
        cleanup=cleanup_command,
        execution_dir=REPO_ROOT,
        payload_paths=[],
        env={},
        artifacts={
            "history_path": str(history_path),
            "backup_path": str(backup_path),
            "backup_dir": str(backup_dir),
            "history_existed": history_exists,
        },
    )


def stage_ability(ability: Ability, caldera_dir: Path, facts: dict[str, str]) -> StagedAbility:
    if ability.ability_id == DUMP_HISTORY_ABILITY_ID:
        return _stage_dump_history_ability(ability, facts)
    if ability.ability_id == AVOID_LOGS_ABILITY_ID:
        return _stage_avoid_logs_ability(ability, facts)

    command = _substitute_placeholders(ability.command, facts)
    cleanup = _substitute_placeholders(ability.cleanup, facts) if ability.cleanup else None
    if not ability.payloads:
        return StagedAbility(
            command=command,
            cleanup=cleanup,
            execution_dir=REPO_ROOT,
            payload_paths=[],
            env={},
            artifacts={},
        )

    payload_source_dir = _ability_payload_source_dir(caldera_dir)
    staging_dir = Path(tempfile.mkdtemp(prefix=f"caldera-{ability.ability_id[:8]}-", dir="/tmp"))
    staged_paths: list[str] = []
    try:
        for payload_name in ability.payloads:
            source_path = payload_source_dir / payload_name
            if not source_path.exists():
                raise FileNotFoundError(f"payload {payload_name!r} not found at {source_path}")
            destination = staging_dir / payload_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination)
            if destination.suffix in {".sh", ".py", ".pl"}:
                destination.chmod(destination.stat().st_mode | 0o111)
            staged_paths.append(str(destination))
        return StagedAbility(
            command=command,
            cleanup=cleanup,
            execution_dir=staging_dir,
            payload_paths=staged_paths,
            env={},
            artifacts={"staging_dir": str(staging_dir)},
        )
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def _build_correlation_queries(ability: Ability, stage: StagedAbility) -> list[CorrelationQuery]:
    if ability.ability_id == PAYLOAD_WIFI_ABILITY_ID and stage.payload_paths:
        # Single-quote escaping ('→'') is sufficient here: stage.execution_dir is a
        # locally generated tempfile path produced by tempfile.mkdtemp, so it will
        # never contain characters that require additional SQL escaping.
        escaped_stage_dir = str(stage.execution_dir).replace("'", "''")
        return [
            CorrelationQuery(
                stream="falco",
                sql=(
                    "SELECT rule, output, output_fields_proc_exepath, output_fields_proc_cmdline, _timestamp "
                    'FROM "falco" '
                    "WHERE rule = 'Execution from Temporary Directory' "
                    # LIKE pattern uniqueness relies on the mkdtemp-generated suffix being unique per run.
                    f"AND output_fields_proc_exepath LIKE '{escaped_stage_dir}/%' "
                    "ORDER BY _timestamp DESC LIMIT 20"
                ),
                expected=True,
            )
        ]

    if ability.ability_id == DUMP_HISTORY_ABILITY_ID:
        # Single-quote escaping ('→'') is sufficient: history_path is a tempfile-backed
        # path generated by mkdtemp and written locally; no other SQL-special chars appear.
        history_path = str(stage.artifacts["history_path"]).replace("'", "''")
        return [
            CorrelationQuery(
                stream="falco",
                sql=(
                    "SELECT rule, output, output_fields_proc_cmdline, _timestamp "
                    'FROM "falco" '
                    "WHERE rule = 'Cross-User Bash History Access' "
                    f"AND output LIKE '%{history_path}%' "
                    "ORDER BY _timestamp DESC LIMIT 20"
                ),
                expected=True,
            )
        ]

    if ability.ability_id == AVOID_LOGS_ABILITY_ID:
        # Single-quote escaping ('→'') is sufficient: history_path is the user's real
        # ~/.bash_history which is a well-known local path free of SQL-special characters.
        history_path = str(stage.artifacts["history_path"]).replace("'", "''")
        return [
            CorrelationQuery(
                stream="falco",
                sql=(
                    "SELECT rule, output, output_fields_proc_cmdline, _timestamp "
                    'FROM "falco" '
                    "WHERE rule = 'Clear Command History (Truncate)' "
                    f"AND output LIKE '%{history_path}%' "
                    "ORDER BY _timestamp DESC LIMIT 20"
                ),
                expected=True,
            )
        ]

    return []


def correlation_expectations_for_ability(ability: Ability) -> list[CorrelationExpectation]:
    expectations: list[CorrelationExpectation] = []
    if ability.ability_id == PAYLOAD_WIFI_ABILITY_ID:
        expectations.append(
            CorrelationExpectation(
                stream="falco",
                expected=True,
                reason="payload-backed abilities run via a staged temp shell to exercise temp execution detection",
            )
        )
    if ability.ability_id == DUMP_HISTORY_ABILITY_ID:
        expectations.append(
            CorrelationExpectation(
                stream="falco",
                expected=True,
                reason="dump-history is staged against a non-home .bash_history path to exercise bash history access detection",
            )
        )
    if ability.ability_id == AVOID_LOGS_ABILITY_ID:
        expectations.append(
            CorrelationExpectation(
                stream="falco",
                expected=True,
                reason="avoid-logs truncates the active .bash_history file to exercise history-clearing detection",
            )
        )
    return expectations


def _merge_environment(overrides: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env.update(overrides)
    return env


def _load_osquery_config_summary() -> dict[str, Any]:
    config = json.loads((REPO_ROOT / "osqueryd.conf").read_text(encoding="utf-8"))
    file_paths = config.get("file_paths", {})
    return {
        "bash_profiles": file_paths.get("bash_profiles", []),
        "file_events_enabled": "file_events" in config.get("schedule", {}),
    }


def _run_osquery_live_query(ability: Ability, stage: StagedAbility) -> dict[str, Any]:
    if ability.ability_id != AVOID_LOGS_ABILITY_ID:
        return {"verified": False, "reason": "no osquery live query defined for this ability"}

    history_path = stage.artifacts.get("history_path")
    if not history_path:
        return {"verified": False, "reason": "history path unavailable"}

    query = f"select path, size from file where path = '{history_path}';"
    completed = subprocess.run(
        ["bash", "./osqueryi-local.sh", query],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {
        "verified": completed.returncode == 0 and history_path in completed.stdout,
        "query": query,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "exit_code": completed.returncode,
    }


def _correlate_logs(
    ability: Ability,
    stage: StagedAbility,
    *,
    enabled: bool,
    search_url: str,
    username: str,
    password: str,
    lookback_seconds: int,
    timeout_seconds: int,
    interval_seconds: int,
) -> dict[str, Any]:
    if not enabled:
        return {"enabled": False, "streams": {}}

    queries = _build_correlation_queries(ability, stage)
    resolved_queries = [
        CorrelationQuery(
            stream=query.stream,
            sql=query.sql,
            expected=query.expected,
        )
        for query in queries
    ]

    responses = _wait_for_logs(
        resolved_queries,
        search_url=search_url,
        username=username,
        password=password,
        start_time=int(time.time() * 1_000_000) - lookback_seconds * 1_000_000,
        end_time=int(time.time() * 1_000_000),
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
    )
    streams = {
        query.stream: {
            "expected": query.expected,
            "verified": bool(response.get("hits")),
            "hits": response.get("hits", []),
        }
        for query in resolved_queries
        for response in [responses[query.stream]]
    }
    expected_streams = {stream: payload for stream, payload in streams.items() if payload["expected"]}
    return {
        "enabled": True,
        "streams": streams,
        "verified": all(stream["verified"] for stream in expected_streams.values()),
        "verified_count": sum(1 for stream in expected_streams.values() if stream["verified"]),
        "expected_count": len(expected_streams),
    }


def _cleanup_stage(stage: StagedAbility) -> None:
    if stage.execution_dir != REPO_ROOT:
        shutil.rmtree(stage.execution_dir, ignore_errors=True)


def execute_ability(
    ability: Ability,
    *,
    caldera_dir: Path,
    facts: dict[str, str],
    timeout_seconds: int,
    service_name: str,
    trace_endpoint: str,
    verify_trace: bool,
    cleanup: bool,
    search_url: str,
    log_search_url: str,
    openobserve_username: str,
    openobserve_password: str,
    verify_timeout_seconds: int,
    verify_interval_seconds: int,
    verify_logs: bool,
    log_verify_timeout_seconds: int,
    log_verify_interval_seconds: int,
    log_lookback_seconds: int,
) -> dict[str, Any]:
    stage = stage_ability(ability, caldera_dir, facts)
    trace_provider, tracer = _make_tracer(service_name, trace_endpoint)
    execution_shell = _prepare_execution_shell(stage, verify_logs=verify_logs)

    cleanup_result: dict[str, Any] | None = None
    started_at = int(time.time() * 1_000_000) - log_lookback_seconds * 1_000_000
    completed: subprocess.CompletedProcess[str]
    try:
        with tracer.start_as_current_span(f"caldera.{ability.ability_id}") as span:
            trace_id = _format_trace_id(span.get_span_context().trace_id)
            span.set_attribute("caldera.ability_id", ability.ability_id)
            span.set_attribute("caldera.ability_name", ability.name)
            span.set_attribute("caldera.tactic", ability.tactic)
            span.set_attribute("caldera.technique_id", ability.technique_id)
            span.set_attribute("caldera.technique_name", ability.technique_name)
            span.set_attribute("caldera.executor", ability.executor)
            span.set_attribute("caldera.command", stage.command)
            span.set_attribute("caldera.payload_count", len(ability.payloads))
            if stage.payload_paths:
                span.set_attribute("caldera.payload_paths", json.dumps(stage.payload_paths))

            completed = subprocess.run(
                [execution_shell, "-lc", stage.command],
                cwd=stage.execution_dir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=_merge_environment(stage.env),
            )
            stdout_preview = completed.stdout[-4000:]
            stderr_preview = completed.stderr[-4000:]
            span.set_attribute("stdout", stdout_preview)
            span.set_attribute("caldera.exit_code", completed.returncode)
            if stderr_preview:
                span.set_attribute("caldera.stderr_preview", stderr_preview)

            if completed.returncode != 0:
                span.set_status(Status(StatusCode.ERROR, f"exit={completed.returncode}"))

            if cleanup and stage.cleanup:
                cleanup_completed = subprocess.run(
                    ["/bin/sh", "-lc", stage.cleanup],
                    cwd=stage.execution_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    env=_merge_environment(stage.env),
                )
                cleanup_result = {
                    "command": stage.cleanup,
                    "exit_code": cleanup_completed.returncode,
                    "stdout": cleanup_completed.stdout[-4000:],
                    "stderr": cleanup_completed.stderr[-4000:],
                }
                span.set_attribute("caldera.cleanup_exit_code", cleanup_completed.returncode)
    finally:
        finished_at = int(time.time() * 1_000_000)
        trace_provider.force_flush()
        # Sleep briefly to ensure the OTEL BatchSpanProcessor has finished exporting
        # before we re-sample end_time; avoids a race where the span timestamp lags
        # behind the wall-clock query window used in _wait_for_trace.
        time.sleep(0.5)
        end_time_us = int(time.time() * 1_000_000)  # noqa: F841  re-captured post-flush

    trace_result: dict[str, Any] = {"trace_id": trace_id, "verified": False}
    try:
        if verify_trace:
            search_response = _wait_for_trace(
                trace_id,
                search_url=search_url,
                username=openobserve_username,
                password=openobserve_password,
                lookback_seconds=DEFAULT_TRACE_LOOKBACK_SECONDS,
                timeout_seconds=verify_timeout_seconds,
                interval_seconds=verify_interval_seconds,
            )
            trace_result["verified"] = bool(search_response.get("hits"))
            trace_result["hits"] = search_response.get("hits", [])

        correlation_result = _correlate_logs(
            ability,
            stage,
            enabled=verify_logs,
            search_url=log_search_url,
            username=openobserve_username,
            password=openobserve_password,
            lookback_seconds=log_lookback_seconds,
            timeout_seconds=log_verify_timeout_seconds,
            interval_seconds=log_verify_interval_seconds,
        )

        return {
            "ability_id": ability.ability_id,
            "ability_name": ability.name,
            "tactic": ability.tactic,
            "technique_id": ability.technique_id,
            "technique_name": ability.technique_name,
            "executor": ability.executor,
            "command": stage.command,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "payloads": ability.payloads,
            "staged_payload_paths": stage.payload_paths,
            "artifacts": stage.artifacts,
            "trace": trace_result,
            "correlation": correlation_result,
            "osquery": {
                "config": _load_osquery_config_summary(),
                "live_query": _run_osquery_live_query(ability, stage),
            },
            "cleanup": cleanup_result,
            "source_path": str(ability.source_path),
            "expected_correlations": [
                {
                    "stream": expectation.stream,
                    "expected": expectation.expected,
                    "reason": expectation.reason,
                }
                for expectation in correlation_expectations_for_ability(ability)
            ],
        }
    finally:
        _cleanup_stage(stage)


def _parse_fact_pairs(pairs: list[str]) -> dict[str, str]:
    facts: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"invalid fact {pair!r}; expected key=value")
        key, value = pair.split("=", 1)
        facts[key] = value
    return facts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run CALDERA host emulation abilities with OTEL traces")
    parser.add_argument("--caldera-dir", type=Path, default=DEFAULT_CALDERA_DIR)

    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap", help="Clone CALDERA and initialize stockpile data")
    bootstrap_parser.set_defaults(handler=handle_bootstrap)

    list_parser = subparsers.add_parser("list-safe-abilities", help="List curated Linux-safe stockpile abilities")
    list_parser.add_argument("--platform", default="linux")
    list_parser.add_argument("--executor", default="sh")
    list_parser.set_defaults(handler=handle_list_safe_abilities)

    run_parser = subparsers.add_parser("run-ability", help="Execute a CALDERA ability on the host and emit an OTEL trace")
    run_parser.add_argument("--ability-id", default=DEFAULT_ABILITY_ID)
    run_parser.add_argument("--platform", default="linux")
    run_parser.add_argument("--executor", default="sh")
    run_parser.add_argument("--fact", action="append", default=[])
    run_parser.add_argument("--timeout-seconds", type=int, default=30)
    run_parser.add_argument("--service-name", default=DEFAULT_TRACE_SERVICE)
    run_parser.add_argument("--trace-endpoint", default=os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", DEFAULT_TRACE_ENDPOINT))
    run_parser.add_argument("--verify-trace", action="store_true")
    run_parser.add_argument("--cleanup", action="store_true")
    run_parser.add_argument("--bootstrap", action="store_true")
    run_parser.add_argument("--search-url", default=os.getenv("OPENOBSERVE_TRACE_SEARCH_URL", DEFAULT_TRACE_SEARCH_URL))
    run_parser.add_argument("--log-search-url", default=os.getenv("OPENOBSERVE_LOG_SEARCH_URL", DEFAULT_LOG_SEARCH_URL))
    run_parser.add_argument("--openobserve-username", default=os.getenv("OPENOBSERVE_USERNAME"))
    run_parser.add_argument("--openobserve-password", default=os.getenv("OPENOBSERVE_PASSWORD"))
    run_parser.add_argument("--verify-timeout-seconds", type=int, default=DEFAULT_TRACE_VERIFY_TIMEOUT_SECONDS)
    run_parser.add_argument("--verify-interval-seconds", type=int, default=DEFAULT_TRACE_VERIFY_INTERVAL_SECONDS)
    run_parser.add_argument("--verify-logs", action="store_true")
    run_parser.add_argument("--log-verify-timeout-seconds", type=int, default=DEFAULT_LOG_VERIFY_TIMEOUT_SECONDS)
    run_parser.add_argument("--log-verify-interval-seconds", type=int, default=DEFAULT_LOG_VERIFY_INTERVAL_SECONDS)
    run_parser.add_argument("--log-lookback-seconds", type=int, default=DEFAULT_LOG_LOOKBACK_SECONDS)
    run_parser.set_defaults(handler=handle_run_ability)

    return parser


def handle_bootstrap(args: argparse.Namespace) -> int:
    bootstrap_caldera_repo(args.caldera_dir)
    print(json.dumps({"caldera_dir": str(args.caldera_dir), "bootstrapped": True}))
    return 0


def handle_list_safe_abilities(args: argparse.Namespace) -> int:
    if args.platform != "linux":
        raise ValueError("list-safe-abilities currently only supports --platform linux")  # TODO: cross-platform support (Windows/macOS) tracked as future feature
    abilities = list_safe_linux_abilities(args.caldera_dir, executor=args.executor)
    payload = [
        {
            "ability_id": ability.ability_id,
            "name": ability.name,
            "tactic": ability.tactic,
            "technique_id": ability.technique_id,
            "technique_name": ability.technique_name,
            "executor": ability.executor,
            "payloads": ability.payloads,
            "source_path": str(ability.source_path),
        }
        for ability in abilities
    ]
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def handle_run_ability(args: argparse.Namespace) -> int:
    if args.bootstrap:
        bootstrap_caldera_repo(args.caldera_dir)

    ability = load_ability(
        args.caldera_dir,
        args.ability_id,
        platform=args.platform,  # TODO: cross-platform support (Windows/macOS) tracked as future feature
        executor=args.executor,
    )
    result = execute_ability(
        ability,
        caldera_dir=args.caldera_dir,
        facts=_parse_fact_pairs(args.fact),
        timeout_seconds=args.timeout_seconds,
        service_name=args.service_name,
        trace_endpoint=args.trace_endpoint,
        verify_trace=args.verify_trace,
        cleanup=args.cleanup,
        search_url=args.search_url,
        log_search_url=args.log_search_url,
        openobserve_username=args.openobserve_username,
        openobserve_password=args.openobserve_password,
        verify_timeout_seconds=args.verify_timeout_seconds,
        verify_interval_seconds=args.verify_interval_seconds,
        verify_logs=args.verify_logs,
        log_verify_timeout_seconds=args.log_verify_timeout_seconds,
        log_verify_interval_seconds=args.log_verify_interval_seconds,
        log_lookback_seconds=args.log_lookback_seconds,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.verify_trace and not result["trace"]["verified"]:
        return 2
    if args.verify_logs and not result["correlation"].get("verified", False):
        return 3
    return 0 if result["exit_code"] == 0 else result["exit_code"]


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.handler(args)
    except (FileNotFoundError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired, error.URLError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
