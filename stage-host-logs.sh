#!/bin/bash
# Stage selected host logs into the repo-local import inbox so OTEL Collector can ingest them on demand.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMPORT_ROOT="$SCRIPT_DIR/.data/host-import/inbox"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

print_info() {
    printf '==> %s\n' "$1"
}

print_warn() {
    printf 'WARN: %s\n' "$1" >&2
}

list_profiles() {
    cat <<'EOF'
Available staging profiles:
  auth       - auth.log and related authentication text logs
  kernel     - kern.log, dmesg, and boot logs
  packages   - apt, dpkg, and alternatives logs
  security   - audit, suricata, crowdsec, and auth-related logs
  desktop    - Xorg, lightdm, gpu-manager, and desktop troubleshooting logs
EOF
}

expand_profile() {
    case "$1" in
        auth)
            printf '%s\n' \
                /var/log/auth.log \
                /var/log/auth.log.1 \
                /var/log/lightdm/*
            ;;
        kernel)
            printf '%s\n' \
                /var/log/kern.log \
                /var/log/kern.log.1 \
                /var/log/dmesg \
                /var/log/dmesg.0 \
                /var/log/boot.log \
                /var/log/boot.log.1
            ;;
        packages)
            printf '%s\n' \
                /var/log/dpkg.log \
                /var/log/dpkg.log.1 \
                /var/log/alternatives.log \
                /var/log/alternatives.log.1 \
                /var/log/apt/history.log \
                /var/log/apt/term.log
            ;;
        security)
            printf '%s\n' \
                /var/log/auth.log \
                /var/log/auth.log.1 \
                /var/log/audit/audit.log \
                /var/log/suricata/*.json \
                /var/log/crowdsec-firewall-bouncer.log \
                /var/log/openvpn/*
            ;;
        desktop)
            printf '%s\n' \
                /var/log/Xorg.0.log \
                /var/log/Xorg.0.log.old \
                /var/log/Xorg.1.log \
                /var/log/Xorg.1.log.old \
                /var/log/gpu-manager.log \
                /var/log/gpu-manager-switch.log \
                /var/log/lightdm/*
            ;;
        *)
            return 1
            ;;
    esac
}

is_binary_log_name() {
    case "$(basename "$1")" in
        wtmp|wtmp.*|btmp|btmp.*|lastlog|faillog)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

classify_import_format() {
    local src="$1"
    local base

    base="$(basename "${src%.gz}")"

    case "$base" in
        *.json)
            printf 'json\n'
            ;;
        auth.log*|kern.log*|syslog*|mail.log*|boot.log*|dmesg*|messages*|secure*|crowdsec-firewall-bouncer.log)
            printf 'syslog\n'
            ;;
        dpkg.log*|alternatives.log*)
            printf 'dpkg\n'
            ;;
        *)
            printf 'plain\n'
            ;;
    esac
}

normalized_target_name() {
    local src="$1"
    local base

    base="${src#/var/log/}"
    base="${base//\//__}"
    base="${base// /_}"
    base="${base%.gz}"

    case "$base" in
        *.log|*.json|*.txt)
            printf '%s\n' "$base"
            ;;
        *)
            printf '%s.log\n' "$base"
            ;;
    esac
}

stage_one() {
    local src="$1"
    local batch_dir="$2"
    local format_dir
    local target

    if is_binary_log_name "$src"; then
        print_warn "Skipping binary login database $src (use last/lastb instead of raw ingestion)"
        return 0
    fi

    if [ ! -e "$src" ]; then
        print_warn "Missing source path: $src"
        return 0
    fi

    if [ -d "$src" ]; then
        print_warn "Skipping directory source: $src"
        return 0
    fi

    if [ ! -r "$src" ]; then
        print_warn "Source is not readable: $src"
        return 0
    fi

    format_dir="$batch_dir/$(classify_import_format "$src")"
    mkdir -p "$format_dir"
    target="$format_dir/$(normalized_target_name "$src")"

    if [ "${src##*.}" = "gz" ]; then
        gzip -dc "$src" > "$target"
    else
        cp "$src" "$target"
    fi

    printf '%s\t%s\n' "$src" "$target" >> "$batch_dir/manifest.tsv"
}

stage_paths() {
    local label="$1"
    shift
    local batch_dir="$IMPORT_ROOT/${TIMESTAMP}-${label}"
    mkdir -p "$batch_dir"
    : > "$batch_dir/manifest.tsv"

    for pattern in "$@"; do
        local matched=0
        for src in $pattern; do
            matched=1
            stage_one "$src" "$batch_dir"
        done
        if [ "$matched" -eq 0 ]; then
            print_warn "No matches for pattern: $pattern"
        fi
    done

    print_info "Staged logs into $batch_dir"
    print_info "OTEL Collector will ingest new files there under job=host_import"
    print_info "Parser-aware subdirectories: syslog, dpkg, json, plain"
}

show_status() {
    mkdir -p "$IMPORT_ROOT"
    find "$IMPORT_ROOT" -maxdepth 1 -mindepth 1 -type d | sort || true
}

clean_imports() {
    rm -rf "$IMPORT_ROOT"
    mkdir -p "$IMPORT_ROOT"
    print_info "Cleared staged host log imports"
}

usage() {
    cat <<'EOF'
Usage:
  ./stage-host-logs.sh profiles
  ./stage-host-logs.sh status
  ./stage-host-logs.sh clean
  ./stage-host-logs.sh stage-profile <profile>
  ./stage-host-logs.sh stage-files <path> [<path> ...]

Examples:
  ./stage-host-logs.sh stage-profile security
  ./stage-host-logs.sh stage-files /var/log/auth.log.1 /var/log/kern.log.1
  sudo ./stage-host-logs.sh stage-files /var/log/audit/audit.log /var/log/suricata/eve.json
EOF
}

mkdir -p "$IMPORT_ROOT"

case "${1:-}" in
    profiles)
        list_profiles
        ;;
    status)
        show_status
        ;;
    clean)
        clean_imports
        ;;
    stage-profile)
        if [ -z "${2:-}" ]; then
            usage
            exit 1
        fi
        mapfile -t paths < <(expand_profile "$2") || {
            print_warn "Unknown profile: $2"
            list_profiles
            exit 1
        }
        stage_paths "$2" "${paths[@]}"
        ;;
    stage-files)
        shift
        if [ "$#" -eq 0 ]; then
            usage
            exit 1
        fi
        stage_paths custom "$@"
        ;;
    *)
        usage
        exit 1
        ;;
esac
