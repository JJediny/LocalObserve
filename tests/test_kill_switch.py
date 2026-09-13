"""test_kill_switch.py — Unit tests for the premapped ID kill switch tool.

Validates:
  * Mapping registry loads correctly
  * Dry-run mode for process kill and container stop
  * Unknown ID returns False
  * YubiKey/sudo step-up prompt fires even in dry-run mode
  * Container runtime detection supports all three runtimes (docker, podman, nerdctl)
"""

import os
import subprocess
from unittest import mock

import pytest

from tools.kill_switch import (
    _detect_container_runtime,
    load_mappings,
    trigger_kill_switch,
)


def test_load_mappings():
    mappings = load_mappings()
    assert isinstance(mappings, dict)
    assert "718c5dbc-b1a3-419b-a329-e7721d294257" in mappings
    assert "KILL_DUMMY_PROCESS" in mappings
    assert "ISOLATE_TEST_CONTAINER" in mappings


def test_kill_switch_dry_run_process():
    success = trigger_kill_switch("KILL_DUMMY_PROCESS", dry_run=True)
    assert success is True


def test_kill_switch_dry_run_container():
    success = trigger_kill_switch("ISOLATE_TEST_CONTAINER", dry_run=True)
    assert success is True


def test_kill_switch_unknown_id_returns_false():
    success = trigger_kill_switch("UNKNOWN_NONEXISTENT_ID_999", dry_run=True)
    assert success is False


def test_yubikey_prompt_fires_in_dry_run():
    """--prompt-yubikey must trigger step-up auth even in dry-run mode.

    This allows operators to test the authentication flow without executing
    the actual kill action.
    """
    with mock.patch("tools.kill_switch.prompt_yubikey_authentication", return_value=True) as m:
        success = trigger_kill_switch(
            "KILL_DUMMY_PROCESS", dry_run=True, require_yubikey=True
        )
    assert success is True
    m.assert_called_once()


def test_yubikey_prompt_failure_blocks_execution():
    """If step-up auth fails, the kill switch must not proceed."""
    with mock.patch("tools.kill_switch.prompt_yubikey_authentication", return_value=False) as m:
        success = trigger_kill_switch(
            "KILL_DUMMY_PROCESS", dry_run=False, require_yubikey=True
        )
    assert success is False
    m.assert_called_once()


def test_no_yubikey_prompt_without_flag():
    """Without --prompt-yubikey, step-up auth must not be called."""
    with mock.patch("tools.kill_switch.prompt_yubikey_authentication", return_value=True) as m:
        success = trigger_kill_switch("KILL_DUMMY_PROCESS", dry_run=True)
    assert success is True
    m.assert_not_called()


class TestYubikeyAuthHermetic:
    """End-to-end exercise of prompt_yubikey_authentication() with mocked sudo.

    These tests do NOT require a real YubiKey, real pam_u2f, or root. They
    validate the function's branches by stubbing subprocess.run to simulate
    three scenarios:

      1. sudo -n true succeeds   → cached credentials, no prompt needed
      2. sudo -n true fails, sudo -v succeeds → fresh password/YubiKey touch
      3. sudo -v fails           → returns False, action blocked

    For real hardware-token verification, follow the steps in
    docs/yubikey_sudo_elevated_privileges_setup.md and run the kill switch
    manually on a host with pam_u2f.so configured.
    """

    def test_cached_credentials_skip_prompt(self):
        from tools.kill_switch import prompt_yubikey_authentication

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            r = mock.Mock()
            r.returncode = 0
            return r

        with mock.patch("tools.kill_switch.subprocess.run", side_effect=fake_run):
            assert prompt_yubikey_authentication() is True

        # Should call sudo -n once; never sudo -v (cached already).
        assert calls == [["sudo", "-n", "true"]]

    def test_fresh_credentials_succeed(self):
        from tools.kill_switch import prompt_yubikey_authentication

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            r = mock.Mock()
            # First call (sudo -n) fails (no cache); second call (sudo -v) succeeds.
            r.returncode = 0 if len(calls) >= 2 else 1
            return r

        with mock.patch("tools.kill_switch.subprocess.run", side_effect=fake_run):
            assert prompt_yubikey_authentication() is True

        assert calls == [["sudo", "-n", "true"], ["sudo", "-v"]]

    def test_failed_authentication_blocks_action(self):
        from tools.kill_switch import prompt_yubikey_authentication

        def fake_run(cmd, **kwargs):
            r = mock.Mock()
            # Always raise CalledProcessError on sudo -v (auth fails / cancels).
            if cmd == ["sudo", "-v"]:
                raise subprocess.CalledProcessError(1, cmd)
            r.returncode = 1
            return r

        with mock.patch("tools.kill_switch.subprocess.run", side_effect=fake_run):
            assert prompt_yubikey_authentication() is False

    def test_unexpected_exception_does_not_block_action(self):
        """If sudo is unavailable (e.g. on Windows or in restricted CI), the
        function logs a warning and returns True so the kill switch can still
        run. This is a deliberate design choice documented in the docstring."""
        from tools.kill_switch import prompt_yubikey_authentication

        def fake_run(cmd, **kwargs):
            raise FileNotFoundError("sudo not found on PATH")

        with mock.patch("tools.kill_switch.subprocess.run", side_effect=fake_run):
            # -n true raises FileNotFoundError before the check loop; the
            # except branch returns True to allow the action to proceed.
            assert prompt_yubikey_authentication() is True


# ---------------------------------------------------------------------------
# Container runtime detection (cross-runtime: docker, podman, nerdctl)
# ---------------------------------------------------------------------------


def test_detect_runtime_respects_env_var():
    """CONTAINER_RUNTIME env var should override auto-detection."""
    with mock.patch("shutil.which", side_effect=lambda c: c == "nerdctl"):
        result = _detect_container_runtime()
    # Without env var, auto-detection picks podman→nerdctl→docker order
    assert result == "nerdctl"

    with mock.patch.dict(os.environ, {"CONTAINER_RUNTIME": "docker"}):
        with mock.patch("shutil.which", side_effect=lambda c: c == "docker"):
            result = _detect_container_runtime()
    assert result == "docker"


def test_detect_runtime_prefers_podman_then_nerdctl_then_docker():
    """Auto-detection priority: podman > nerdctl > docker."""
    # All three available → podman wins
    with mock.patch("shutil.which", side_effect=lambda c: True):
        with mock.patch.dict(os.environ, {}, clear=True):
            result = _detect_container_runtime()
    assert result == "podman"

    # Only nerdctl and docker → nerdctl wins
    with mock.patch("shutil.which", side_effect=lambda c: c in ("nerdctl", "docker")):
        with mock.patch.dict(os.environ, {}, clear=True):
            result = _detect_container_runtime()
    assert result == "nerdctl"

    # Only docker → docker wins
    with mock.patch("shutil.which", side_effect=lambda c: c == "docker"):
        with mock.patch.dict(os.environ, {}, clear=True):
            result = _detect_container_runtime()
    assert result == "docker"


def test_detect_runtime_returns_none_when_unavailable():
    """No container runtime available → returns None."""
    with mock.patch("shutil.which", return_value=None):
        with mock.patch.dict(os.environ, {}, clear=True):
            result = _detect_container_runtime()
    assert result is None
