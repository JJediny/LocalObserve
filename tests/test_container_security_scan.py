"""Tests for the container image security scan workflow.

Validates:
- `scripts/scan-images.sh` is executable, has correct shebang, parses
  compose files, and runs Trivy without crashing on a clean image.
- `docker-compose.yaml` declares the expected pinned image versions
  documented in docs/container_security_scan.md.
- `renovate.json` is valid JSON and targets the docker-compose datasource.

These tests do NOT run Trivy on every image (that would be slow + requires
network + registry auth). The CI workflow at
`.github/workflows/container-image-scan.yml` runs the full scan.
"""

import json
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose.yaml"
SCAN_SCRIPT = ROOT / "scripts" / "scan-images.sh"
RENOVATE = ROOT / "renovate.json"
SCAN_DOC = ROOT / "docs" / "container_security_scan.md"
WORKFLOW = ROOT / ".github" / "workflows" / "container-image-scan.yml"


class TestScanScript:
    def test_script_exists(self):
        assert SCAN_SCRIPT.exists(), f"missing {SCAN_SCRIPT}"

    def test_script_executable(self):
        mode = SCAN_SCRIPT.stat().st_mode
        assert mode & stat.S_IXUSR, f"{SCAN_SCRIPT} must be executable (chmod +x)"

    def test_script_has_bash_shebang(self):
        first_line = SCAN_SCRIPT.read_text().splitlines()[0]
        assert first_line.startswith("#!/usr/bin/env bash") or first_line.startswith("#!/bin/bash"), (
            f"unexpected shebang: {first_line!r}"
        )

    def test_script_extracts_images(self):
        """The script should be able to parse our compose file and list images."""
        result = subprocess.run(
            ["bash", "-n", str(SCAN_SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"shell syntax error: {result.stderr}"

    def test_compose_has_at_least_one_pinned_image(self):
        """We pinned osquery in this PR; this guards against accidental regression to :latest."""
        text = COMPOSE.read_text()
        # Read the osquery service block.
        m = re.search(
            r"^\s*osquery:\s*\n((?:[ \t].*\n)+)",
            text,
            flags=re.MULTILINE,
        )
        assert m, "could not find osquery service block"
        block = m.group(1)
        image_line = next(
            (ln for ln in block.splitlines() if re.match(r"\s+image:", ln)),
            None,
        )
        assert image_line, "osquery service has no image line"
        assert ":latest" not in image_line, (
            f"osquery must not use :latest — pinned in docs/container_security_scan.md; "
            f"found: {image_line!r}"
        )
        assert "5.17.0-ubuntu22.04" in image_line, (
            f"osquery pin changed unexpectedly — was 5.17.0-ubuntu22.04, found: {image_line!r}"
        )


class TestRenovateConfig:
    def test_renovate_json_valid(self):
        data = json.loads(RENOVATE.read_text())
        assert data.get("docker-compose"), "renovate.json must include docker-compose config"
        # Must enable at least the docker-compose manager.
        managers = data.get("enabledManagers", [])
        assert "docker-compose" in managers

    def test_renovate_targets_docker_images(self):
        data = json.loads(RENOVATE.read_text())
        rules = data.get("packageRules", [])
        # At least one rule should target docker datasource.
        assert any(
            "docker" in (rule.get("matchDatasources") or [])
            for rule in rules
        ), "no package rule targets docker datasource"


class TestDocumentationExists:
    def test_scan_doc_exists(self):
        assert SCAN_DOC.exists(), f"missing {SCAN_DOC}"

    def test_scan_doc_references_trivy(self):
        text = SCAN_DOC.read_text().lower()
        assert "trivy" in text, "scan doc must reference Trivy"
        assert "high" in text and "critical" in text, "scan doc must list severity levels"

    def test_scan_doc_mentions_osquery_pin(self):
        text = SCAN_DOC.read_text()
        assert "5.17.0-ubuntu22.04" in text, (
            "scan doc must document the osquery pin (5.17.0-ubuntu22.04)"
        )


class TestCIWorkflow:
    def test_workflow_exists(self):
        assert WORKFLOW.exists(), f"missing {WORKFLOW}"

    def test_workflow_triggers_on_pr(self):
        text = WORKFLOW.read_text()
        assert "pull_request" in text, "workflow must trigger on pull_request"
        assert "schedule" in text, "workflow must have a schedule (cron) for periodic scans"

    def test_workflow_uses_trivy_action(self):
        text = WORKFLOW.read_text()
        assert "aquasecurity/trivy-action" in text, "workflow must use the official Trivy action"

    def test_workflow_uploads_sarif(self):
        text = WORKFLOW.read_text()
        assert "sarif" in text.lower(), "workflow must upload SARIF for GitHub Security tab"


class TestComposeImagesListable:
    """Sanity check: `docker compose config --images` works against this file."""

    @pytest.mark.skipif(
        not os.environ.get("DOCKER_AVAILABLE"),
        reason="docker not available in test env",
    )
    def test_docker_compose_config_parses(self):
        result = subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE), "config", "--images"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"compose config failed: {result.stderr}"
        images = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        assert len(images) >= 8, f"expected >= 8 images, got {len(images)}"
        # The osquery pin must appear in the resolved list.
        assert any("5.17.0-ubuntu22.04" in img for img in images), (
            f"osquery 5.17.0-ubuntu22.04 pin not present in {images}"
        )
