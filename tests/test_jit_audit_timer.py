"""Static checks for the scheduled JIT audit revocation cycle (M-26-14 Req-3).

`tools/compliance_rbac_jit.py audit` is the ONLY revocation path for expired JIT
tickets; unscheduled expiry produced a lingering admin user in the 2026-10 #82
review. These tests keep the systemd units, installer, and Taskfile wiring in
sync with the tool — mirroring the content-assertion style used by
test_container_image_release.py.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "systemd" / "localobserve-jit-audit.service"
TIMER = ROOT / "systemd" / "localobserve-jit-audit.timer"
INSTALLER = ROOT / "scripts" / "install-jit-timer.sh"
TASKFILE = ROOT / "Taskfile.yml"


def test_units_and_installer_exist():
    assert SERVICE.exists(), "missing systemd/localobserve-jit-audit.service"
    assert TIMER.exists(), "missing systemd/localobserve-jit-audit.timer"
    assert INSTALLER.exists(), "missing scripts/install-jit-timer.sh"


def test_service_invokes_the_audit_cycle():
    text = SERVICE.read_text(encoding="utf-8")
    assert "Type=oneshot" in text
    # Must run the same command the docs/Taskfile advertise — a rename of the
    # tool or subcommand must fail this test, not rot silently in a timer.
    assert re.search(r"python3\s+\S+/tools/compliance_rbac_jit\.py\s+audit", text)
    assert "WorkingDirectory=/home/john/LocalObserve" in text  # rewritten by installer


def test_timer_is_periodic_persistent_and_installed():
    text = TIMER.read_text(encoding="utf-8")
    assert "OnUnitActiveSec=" in text, "timer must recur, not just boot once"
    assert "Persistent=true" in text, "missed cycles must fire after downtime"
    assert "WantedBy=timers.target" in text


def test_installer_is_valid_bash_localizes_paths_and_targets_user_scope():
    result = subprocess.run(["bash", "-n", str(INSTALLER)], capture_output=True, text=True)
    assert result.returncode == 0, f"installer syntax error: {result.stderr}"
    text = INSTALLER.read_text(encoding="utf-8")
    assert "systemctl --user" in text, "must install at user scope (no root)"
    assert "systemctl --user enable --now localobserve-jit-audit.timer" in text
    # Path localization convention (matches install-logrotate.sh).
    assert "s|/home/john/LocalObserve|${REPO_ROOT}|g" in text


def test_taskfile_exposes_install_status_and_remove():
    text = TASKFILE.read_text(encoding="utf-8")
    assert "install-jit-timer" in text
    assert "scripts/install-jit-timer.sh" in text
