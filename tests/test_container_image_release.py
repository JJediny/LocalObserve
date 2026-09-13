"""Static checks for self-authored image release automation."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "release-container-images.yml"
DOCKERFILE = ROOT / "alerts" / "webhook" / "Dockerfile"
DOC = ROOT / "docs" / "container_image_releases.md"


def test_release_workflow_and_real_dockerfile_exist():
    assert WORKFLOW.exists()
    assert DOCKERFILE.exists()
    assert DOC.exists()


def test_webhook_runtime_bases_are_digest_pinned():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "FROM almir/webhook@sha256:" in text
    assert "FROM alpine@sha256:" in text
    assert "FROM almir/webhook:latest" not in text


def test_release_is_tag_driven_and_semver_validated():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "tags:" in text
    assert "'v*.*.*'" in text
    assert "^v[0-9]+\\.[0-9]+\\.[0-9]+" in text
    assert "Invalid release tag" in text


def test_release_pushes_only_the_buildable_self_authored_image():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "localobserve-webhook" in text
    assert "./alerts/webhook" in text
    assert "./alerts/webhook/Dockerfile" in text
    assert "config/image_sourcing.yaml" not in text
    assert "Dockerfile.openobserve.distroless" not in text


def test_release_has_registry_security_and_attestations():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "packages: write" in text
    assert "id-token: write" in text
    assert "attestations: write" in text
    assert "docker/login-action@v3" in text
    assert "docker/metadata-action@v5" in text
    assert "docker/build-push-action@v6" in text
    assert "actions/attest-build-provenance@v2" in text
    assert "provenance: mode=max" in text
    assert "sbom: true" in text


def test_release_creates_github_release_for_pushed_version_tags():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "gh release create" in text
    assert "--generate-notes" in text
    assert "startsWith(github.ref, 'refs/tags/v')" in text
