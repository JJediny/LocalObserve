#!/usr/bin/env bash
# Migrate legacy bind-mounted OpenObserve data to the Compose named volume.
#
# Rootless Podman maps container root to the unprivileged host user, while
# Docker may have created the bind-mounted metadata directory as real root.
# A runtime-managed named volume avoids that ownership mismatch without sudo.
#
# Usage:
#   RUNTIME=docker bash scripts/migrate-openobserve-data.sh
#   RUNTIME=podman PROJECT=localobserve-podman bash scripts/migrate-openobserve-data.sh
#
# The Compose stack is stopped before the copy so SQLite metadata is not copied
# mid-write. Use --force when the destination volume already has content.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=runtime-compose.sh
source "$SCRIPT_DIR/runtime-compose.sh"

RUNTIME="${RUNTIME:-docker}"
PROJECT="${PROJECT:-localobserve}"
SOURCE_DIR="${OPENOBSERVE_DATA_DIR:-$ROOT/.data/openobserve-data}"
DEST_VOLUME="${OPENOBSERVE_VOLUME:-localobserve_openobserve_data}"
HELPER_IMAGE="${OPENOBSERVE_MIGRATION_IMAGE:-alpine:3.21}"
FORCE=0
START=0
DRY_RUN=0

usage() {
    echo "Usage: $0 [--project NAME] [--source PATH] [--force] [--start] [--dry-run]"
}

while (($#)); do
    case "$1" in
        --project)
            [[ $# -ge 2 ]] || { echo "--project requires a value" >&2; exit 2; }
            PROJECT="$2"
            shift 2
            ;;
        --source)
            [[ $# -ge 2 ]] || { echo "--source requires a value" >&2; exit 2; }
            SOURCE_DIR="$2"
            shift 2
            ;;
        --force)
            FORCE=1
            shift
            ;;
        --start)
            START=1
            shift
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ ! -d "$SOURCE_DIR" ]]; then
    if ! "$BINARY" volume inspect "$DEST_VOLUME" >/dev/null 2>&1; then
        echo "==> No legacy bind-mounted data found; initializing named volume: $DEST_VOLUME"
        "$BINARY" volume create "$DEST_VOLUME" >/dev/null
        echo "OK: OpenObserve named volume initialized."
    else
        echo "OK: OpenObserve named volume already exists; no legacy directory to migrate."
    fi
    if ((START)); then
        echo "==> Starting Compose project: $PROJECT"
        COMPOSE_PROJECT_NAME="$PROJECT" runtime_compose "$RUNTIME" up -d
    fi
    exit 0
fi

BINARY="$(runtime_binary "$RUNTIME")"

copy_plan() {
    printf '%s\n' \
        "$BINARY stop <containers labeled $PROJECT>" \
        "COMPOSE_PROJECT_NAME=$PROJECT $RUNTIME compose volume create openobserve_data" \
        "$BINARY run --rm -v $DEST_VOLUME:/localobserve-volume:z -v $SOURCE_DIR:/localobserve-data:ro $HELPER_IMAGE sh -c 'copy legacy data; verify SQLite files'"
}

if ((DRY_RUN)); then
    echo "Migration plan (no changes made):"
    copy_plan
    exit 0
fi

echo "==> Stopping Compose project: $PROJECT"
PROJECT_CONTAINERS="$("$BINARY" ps -q --filter "label=com.docker.compose.project=$PROJECT")"
if [[ -n "$PROJECT_CONTAINERS" ]]; then
    "$BINARY" stop $PROJECT_CONTAINERS
fi

echo "==> Ensuring named volume exists: $DEST_VOLUME"
if ! "$BINARY" volume inspect "$DEST_VOLUME" >/dev/null 2>&1; then
    "$BINARY" volume create "$DEST_VOLUME" >/dev/null
fi

echo "==> Copying $SOURCE_DIR -> $DEST_VOLUME"
FORCE="$FORCE" "$BINARY" run --rm \
    --name "localobserve-openobserve-migration-$$" \
    -v "$DEST_VOLUME:/localobserve-volume:z" \
    -v "$SOURCE_DIR:/localobserve-data:ro" \
    "$HELPER_IMAGE" sh -eu -c '
        dst=/localobserve-volume
        src=/localobserve-data
        if [ -n "$(ls -A "$dst" 2>/dev/null)" ] && [ "$FORCE" != "1" ]; then
            echo "Destination volume is not empty. Re-run with --force to overwrite it." >&2
            exit 42
        fi
        rm -rf "$dst"/* "$dst"/.[!.]* "$dst"/..?* 2>/dev/null || true
        cp -a "$src"/. "$dst"/

        test -f "$dst/db/metadata.sqlite" || {
            echo "Migration failed: metadata.sqlite missing from destination volume." >&2
            exit 1
        }

        # A SQLite database is only safely restartable after its WAL sidecar
        # files are present in the same volume.
        touch "$dst/db/metadata.sqlite"
    '

if ((START)); then
    echo "==> Starting migrated Compose project: $PROJECT"
    COMPOSE_PROJECT_NAME="$PROJECT" runtime_compose "$RUNTIME" up -d
fi

echo "OK: OpenObserve data migrated to $DEST_VOLUME."
echo "Start it with: COMPOSE_PROJECT_NAME=$PROJECT $RUNTIME compose up -d"
