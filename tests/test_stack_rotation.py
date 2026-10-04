from __future__ import annotations

"""
test_stack_rotation.py

Validates log rotation configuration and mechanics:
1. scripts/logrotate-localobserve.conf syntax and directives
2. copytruncate usage across all tailed log paths
3. scripts/install-logrotate.sh presence and execution
4. Bounded rotation caps to prevent unbounded disk growth (Issue #100)
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LOGROTATE_CONF = REPO_ROOT / "scripts" / "logrotate-localobserve.conf"
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install-logrotate.sh"


def test_logrotate_config_exists() -> None:
    """logrotate configuration file must exist in scripts/."""
    assert LOGROTATE_CONF.exists(), "scripts/logrotate-localobserve.conf missing"


def test_install_logrotate_script_exists_and_executable() -> None:
    """scripts/install-logrotate.sh must exist and be executable."""
    assert INSTALL_SCRIPT.exists(), "scripts/install-logrotate.sh missing"
    mode = INSTALL_SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR, "scripts/install-logrotate.sh must be executable by owner"


def test_logrotate_syntax_validation() -> None:
    """scripts/logrotate-localobserve.conf must pass logrotate -d validation."""
    if not shutil.which("logrotate"):
        pytest.skip("logrotate binary not available on this host")

    res = subprocess.run(
        ["bash", str(INSTALL_SCRIPT), "--dry-run"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"logrotate validation failed:\n{res.stderr}"
    assert "Logrotate configuration is valid" in res.stdout


def test_all_log_sections_use_copytruncate() -> None:
    """All logrotate sections must specify copytruncate.

    copytruncate is required because the OpenTelemetry Collector's file_log
    receiver maintains open file descriptors on the active log files.
    Renaming files breaks tailing continuity unless copytruncate preserves
    the inode and active file path.
    """
    content = LOGROTATE_CONF.read_text()
    sections = [s.strip() for s in content.split("}") if "{" in s]
    assert len(sections) >= 3, "Expected at least 3 logrotate sections"

    for sec in sections:
        header = sec.split("{")[0].strip()
        assert "copytruncate" in sec, (
            f"Section '{header}' is missing 'copytruncate' directive"
        )


def test_all_log_sections_specify_bounded_size() -> None:
    """All log sections must specify maxsize or size caps to prevent unbounded SSD growth."""
    content = LOGROTATE_CONF.read_text()
    sections = [s.strip() for s in content.split("}") if "{" in s]

    for sec in sections:
        header = sec.split("{")[0].strip()
        assert "maxsize" in sec or "size" in sec, (
            f"Section '{header}' is missing 'maxsize' or 'size' cap"
        )


def test_osquery_results_log_is_capped_at_or_below_50m() -> None:
    """osqueryd.results.log must be rotated at or below 50M to prevent unbounded growth (Issue #100)."""
    content = LOGROTATE_CONF.read_text()
    assert "osqueryd.results.log" in content

    # Locate the osquery block
    osquery_sec = None
    for sec in content.split("}"):
        if "osqueryd.results.log" in sec:
            osquery_sec = sec
            break

    assert osquery_sec is not None, "osquery section not found in logrotate config"
    assert "maxsize 50M" in osquery_sec or "size 50M" in osquery_sec, (
        "osqueryd.results.log rotation must be bounded at 50M"
    )


def test_copytruncate_simulation_preserves_tailing_continuity(tmp_path: Path) -> None:
    """Verify that copytruncate semantics allow continued append and read without inode changes."""
    log_file = tmp_path / "test.log"
    rot_file = tmp_path / "test.log.1"

    # Step 1: Write initial lines
    with open(log_file, "w") as f:
        f.write('{"event": "start", "seq": 1}\n')
        f.write('{"event": "auth", "seq": 2}\n')

    initial_inode = os.stat(log_file).st_ino

    # Step 2: Simulate copytruncate (copy active -> .1, then truncate active to 0)
    shutil.copyfile(log_file, rot_file)
    with open(log_file, "r+") as f:
        f.truncate(0)

    post_truncate_inode = os.stat(log_file).st_ino
    assert initial_inode == post_truncate_inode, "Inode must remain unchanged across copytruncate"
    assert os.path.getsize(log_file) == 0, "Log file size must be 0 after truncate"
    assert os.path.getsize(rot_file) > 0, "Rotated file must contain preserved records"

    # Step 3: Append new records to active file
    with open(log_file, "a") as f:
        f.write('{"event": "post_rotation", "seq": 3}\n')

    with open(log_file, "r") as f:
        lines = f.readlines()

    assert len(lines) == 1
    assert "post_rotation" in lines[0]
