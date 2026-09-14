"""Static policy checks for the caldera-detection-coverage workflow.

The build-and-test job is a verify-only gate. It must not auto-mutate
main, must not push, and must fail (not silently fix) when uv.lock is
out of sync with pyproject.toml.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "caldera-detection-coverage.yml"


def _load():
    assert WORKFLOW.exists(), f"Workflow missing: {WORKFLOW}"
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_workflow_validates_and_has_build_and_test_job():
    data = _load()
    assert "jobs" in data
    assert "build-and-test" in data["jobs"], "build-and-test job is required"


def test_build_and_test_job_is_verify_only_no_contents_write():
    data = _load()
    job = data["jobs"]["build-and-test"]
    perms = job.get("permissions") or {}
    contents = perms.get("contents") if isinstance(perms, dict) else None
    assert contents != "write", (
        "build-and-test must not have contents: write; "
        "the job is verify-only and must not push to main"
    )


def test_build_and_test_uses_uv_lock_check():
    data = _load()
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "uv lock --check" in text, (
        "build-and-test must use `uv lock --check` to verify the lockfile; "
        "auto-upgrade of dependencies is no longer in scope for this workflow"
    )
    assert "uv lock --upgrade" not in text, (
        "build-and-test must not run `uv lock --upgrade`; "
        "lockfile maintenance is operator-driven"
    )


def test_build_and_test_does_not_push_or_commit():
    data = _load()
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "Commit & Push uv.lock Changes" not in text, (
        "The auto-commit-and-push step has been removed; lockfile drift is "
        "an operator action, not an unattended workflow side effect"
    )
    # No `git push` anywhere in the build-and-test job body.
    job = data["jobs"]["build-and-test"]
    for step in job.get("steps", []):
        run = step.get("run") or ""
        assert "git push" not in run, (
            f"Step {step.get('name')!r} in build-and-test runs `git push`; "
            "this job is verify-only"
        )


def test_build_and_test_runs_compliance_validation():
    data = _load()
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "tests/test_compliance_validation.py" in text, (
        "build-and-test must still run the compliance validation suite"
    )
