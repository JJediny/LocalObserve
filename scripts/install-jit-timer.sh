#!/usr/bin/env bash
# install-jit-timer.sh — Install the LocalObserve JIT audit systemd *user* timer.
#
# Runs `tools/compliance_rbac_jit.py audit` hourly so expired JIT access tickets
# are actually revoked (M-26-14 Req-3). Unscheduled expiry was the failure mode
# behind the lingering security_auditor admin user found in the #82 review.
#
# User scope: no root required, no /etc changes. See the enable-linger note on
# install for headless hosts.
#
# Usage:
#   bash scripts/install-jit-timer.sh            # install + enable (user scope)
#   bash scripts/install-jit-timer.sh --dry-run  # generate + verify units, install nothing
#   bash scripts/install-jit-timer.sh --status   # show timer state
#   bash scripts/install-jit-timer.sh --remove   # disable + uninstall

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNITS=(localobserve-jit-audit.service localobserve-jit-audit.timer)

generate_units() {
    local target_dir="$1"
    mkdir -p "$target_dir"
    for unit in "${UNITS[@]}"; do
        # Same path-rewrite convention as install-logrotate.sh: the repo copies
        # carry the default checkout location and are localized on install.
        sed "s|/home/john/LocalObserve|${REPO_ROOT}|g" "${REPO_ROOT}/systemd/${unit}" > "${target_dir}/${unit}"
    done
}

verify_units() {
    local dir="$1"
    if command -v systemd-analyze >/dev/null 2>&1; then
        systemd-analyze verify "${dir}/localobserve-jit-audit.service"
        systemd-analyze verify "${dir}/localobserve-jit-audit.timer"
        echo "[+] systemd-analyze verify: units OK"
    else
        echo "[!] systemd-analyze not found; syntax verification skipped." >&2
    fi
}

case "${1:-}" in
    --dry-run)
        tmp_dir=$(mktemp -d)
        generate_units "$tmp_dir"
        echo "[*] Generated for REPO_ROOT=${REPO_ROOT}:"
        grep -HnE 'ExecStart|WorkingDirectory|OnUnitActiveSec|Persistent' "$tmp_dir"/*
        verify_units "$tmp_dir" || { rm -rf "$tmp_dir"; exit 1; }
        rm -rf "$tmp_dir"
        echo "[+] Dry run complete — nothing installed."
        exit 0
        ;;
    --status)
        systemctl --user list-timers 'localobserve-jit-audit*' --no-pager || true
        systemctl --user is-enabled localobserve-jit-audit.timer 2>/dev/null || echo "[!] Timer not enabled."
        exit 0
        ;;
    --remove)
        systemctl --user disable --now localobserve-jit-audit.timer 2>/dev/null || true
        rm -f "${UNIT_DIR}/localobserve-jit-audit.service" "${UNIT_DIR}/localobserve-jit-audit.timer"
        systemctl --user daemon-reload
        echo "[+] JIT audit timer disabled and unit files removed."
        exit 0
        ;;
    --install|"")
        generate_units "$UNIT_DIR"
        verify_units "$UNIT_DIR"
        systemctl --user daemon-reload
        systemctl --user enable --now localobserve-jit-audit.timer
        echo "[+] Installed ${UNITS[*]} -> ${UNIT_DIR}"
        echo "[+] Hourly JIT expiry revocation is active."
        echo "[!] Headless hosts: user services stop at logout unless lingering is on:"
        echo "      loginctl enable-linger $(id -un)"
        exit 0
        ;;
    *)
        echo "Usage: $0 [--install|--dry-run|--status|--remove]" >&2
        exit 1
        ;;
esac
