# Self-authored container image releases

LocalObserve publishes only images that have a real Dockerfile in this repository.
The release workflow is `.github/workflows/release-container-images.yml`.

## Published image

| Image | Build context | Dockerfile |
|---|---|---|
| `ghcr.io/jjediny/localobserve-webhook` | `./alerts/webhook` | `./alerts/webhook/Dockerfile` |

The image is built from the repository's alert receiver Dockerfile. Its
runtime stage is pinned to an Alpine digest; the upstream webhook binary is
copied from a separately pinned build stage instead of inheriting the
upstream image's mutable runtime base. The aspirational entries in
`config/image_sourcing.yaml` are not release targets until their Dockerfiles
are implemented and independently scanned.

## Release a version

Create and push a SemVer tag from a clean `main` commit:

```bash
git checkout main
git pull --ff-only origin main
git tag -a v1.0.0 -m "LocalObserve v1.0.0"
git push origin v1.0.0
```

The workflow then:

1. Validates the `vMAJOR.MINOR.PATCH` tag format.
2. Builds `localobserve-webhook` for `linux/amd64` with Buildx.
3. Runs Trivy against the built image and blocks the release on any
   CRITICAL vulnerability.
4. Publishes the version tag, normalized SemVer tag, minor tag, and
   `latest` for stable releases to GHCR.
5. Publishes BuildKit provenance and SBOM attestations.
6. Creates a GitHub release with generated notes.

The 2026-09-13 local scan of the hardened image reported **0 CRITICAL and
24 HIGH** findings. The HIGH findings are inherited from the upstream Go
webhook binary and are documented; the release gate intentionally blocks only
CRITICAL findings so known upstream-rebuild-only Go issues do not prevent a
version from being published.

Example pull:

```bash
docker pull ghcr.io/jjediny/localobserve-webhook:1.0.0
```

The package is private until its GHCR visibility is changed or an operator
logs in with a token that has `read:packages`:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u JJediny --password-stdin
docker pull ghcr.io/jjediny/localobserve-webhook:1.0.0
```

## Adding another self-authored image

1. Add and test a real Dockerfile in the repository.
2. Add one `matrix.include` entry to the release workflow with its image name,
   context, and Dockerfile path.
3. Add a static test for the new path and run Trivy against the built image.
4. Update `docker-compose.yaml` and this document only after the image is
   reproducibly buildable.

Do not add vendor images or the unimplemented distroless targets to the
release matrix. This keeps the release action limited to artifacts owned and
built by LocalObserve.
