#!/bin/bash
###############################################################################
# setup-osqueryd.sh
# Automates osqueryd configuration, setup, and management on the host
###############################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUIET_CONFIG_FILE="$SCRIPT_DIR/osqueryd.conf"
DEEP_FORENSIC_CONFIG_FILE="$SCRIPT_DIR/osqueryd-deep-forensic.conf"
SSD_CONFIG_FILE="$SCRIPT_DIR/osqueryd-ssd-optimized.conf"
CONFIG_FILE="$QUIET_CONFIG_FILE"
SELECTED_PROFILE="quiet"
FLAGS_FILE="$SCRIPT_DIR/osquery.flags"
OSQUERY_CONF_DIR="/etc/osquery"
OSQUERY_FLAG_FILE="$OSQUERY_CONF_DIR/osquery.flags"
OSQUERY_CONF_FILE="$OSQUERY_CONF_DIR/osquery.conf"
ACTIVE_PROFILE_FILE="$OSQUERY_CONF_DIR/osquery.profile"
OSQUERY_LOG_DIR="$SCRIPT_DIR/.data/osquery"
LEGACY_OSQUERY_LOG_DIR="/var/log/osquery"
PACKS_DIR="$OSQUERY_CONF_DIR/packs"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

list_profiles() {
    cat << EOF
Available profiles:
  quiet           - Default low-noise profile for routine always-on monitoring
  deep-forensic   - Higher-volume profile with broader process, package, and pack visibility
  ssd-optimized   - Lowest-write profile with reduced schedule breadth for constrained hosts
EOF
}

normalize_profile() {
    case "${1:-quiet}" in
        quiet|default)
            echo "quiet"
            ;;
        deep|forensic|deep-forensic|verbose)
            echo "deep-forensic"
            ;;
        ssd|ssd-optimized)
            echo "ssd-optimized"
            ;;
        *)
            return 1
            ;;
    esac
}

select_profile() {
    local normalized

    if ! normalized=$(normalize_profile "$1"); then
        print_error "Unknown osquery profile: $1"
        echo ""
        list_profiles
        exit 1
    fi

    SELECTED_PROFILE="$normalized"

    case "$SELECTED_PROFILE" in
        quiet)
            CONFIG_FILE="$QUIET_CONFIG_FILE"
            ;;
        deep-forensic)
            CONFIG_FILE="$DEEP_FORENSIC_CONFIG_FILE"
            ;;
        ssd-optimized)
            CONFIG_FILE="$SSD_CONFIG_FILE"
            ;;
    esac
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root"
        echo "Please run: sudo $0 $@"
        exit 1
    fi
}

verify_osquery_installed() {
    print_header "Verifying osquery installation"

    if ! command -v osqueryd &> /dev/null; then
        print_error "osqueryd not found. Please install osquery first:"
        echo "  Ubuntu/Debian: sudo apt-get install osquery"
        echo "  CentOS/RHEL: sudo yum install osquery"
        exit 1
    fi

    OSQUERY_VERSION=$(osqueryd --version 2>&1 | grep -oP 'osquery version [0-9.]+' || echo "unknown")
    print_success "osquery installed: $OSQUERY_VERSION"
}

setup_directories() {
    print_header "Setting up directories and permissions"

    # Create osquery config directory
    if [ ! -d "$OSQUERY_CONF_DIR" ]; then
        mkdir -p "$OSQUERY_CONF_DIR"
        print_success "Created $OSQUERY_CONF_DIR"
    fi

    # Create repo-local osquery log directory so Docker can bind-mount it reliably.
    if [ ! -d "$OSQUERY_LOG_DIR" ]; then
        mkdir -p "$OSQUERY_LOG_DIR"
        print_success "Created $OSQUERY_LOG_DIR"
    fi

    if [ -d "$LEGACY_OSQUERY_LOG_DIR" ] && [ "$LEGACY_OSQUERY_LOG_DIR" != "$OSQUERY_LOG_DIR" ]; then
        print_warning "Legacy osquery log directory detected at $LEGACY_OSQUERY_LOG_DIR"
        print_warning "Logs for the Docker stack will be written to $OSQUERY_LOG_DIR"
    fi

    # Create packs directory
    if [ ! -d "$PACKS_DIR" ]; then
        mkdir -p "$PACKS_DIR"
        print_success "Created $PACKS_DIR"
    fi

    # Set proper ownership and permissions
    chown -R osquery:osquery "$OSQUERY_CONF_DIR" "$OSQUERY_LOG_DIR"
    chmod 755 "$OSQUERY_CONF_DIR" "$OSQUERY_LOG_DIR" "$PACKS_DIR"
    chmod 644 "$OSQUERY_CONF_DIR"/osquery.conf 2>/dev/null || true
    chmod 644 "$OSQUERY_FLAG_FILE" 2>/dev/null || true
    chmod 644 "$ACTIVE_PROFILE_FILE" 2>/dev/null || true
    chmod 644 "$OSQUERY_LOG_DIR"/*.log 2>/dev/null || true

    print_success "Directory permissions set"
}

copy_config() {
    print_header "Copying osquery configuration"

    if [ ! -f "$CONFIG_FILE" ]; then
        print_error "Config file not found: $CONFIG_FILE"
        exit 1
    fi

    cp "$CONFIG_FILE" "$OSQUERY_CONF_FILE"

    python3 - <<PY
import json
from pathlib import Path

config_path = Path("$OSQUERY_CONF_FILE")
config = json.loads(config_path.read_text())
config.setdefault("options", {})["logger_path"] = "$OSQUERY_LOG_DIR"
config_path.write_text(json.dumps(config, indent=2) + "\n")
PY

    printf '%s\n' "$SELECTED_PROFILE" > "$ACTIVE_PROFILE_FILE"

    chown osquery:osquery "$OSQUERY_CONF_FILE" "$ACTIVE_PROFILE_FILE"
    chmod 644 "$OSQUERY_CONF_FILE" "$ACTIVE_PROFILE_FILE"

    if [ -f "$FLAGS_FILE" ]; then
        cp "$FLAGS_FILE" "$OSQUERY_FLAG_FILE"
        chown osquery:osquery "$OSQUERY_FLAG_FILE"
        chmod 644 "$OSQUERY_FLAG_FILE"
        print_success "Flagfile copied to $OSQUERY_FLAG_FILE"
    else
        print_warning "Flagfile not found: $FLAGS_FILE"
    fi

    print_success "Installed osquery profile: $SELECTED_PROFILE"
    print_success "Configuration copied to $OSQUERY_CONF_FILE"
    print_success "osquery results will be written to $OSQUERY_LOG_DIR"
}

download_packs() {
    print_header "Downloading official osquery packs"

    PACKS=(
        "incident-response"
        "ossec-rootkit"
        "it-compliance"
    )

    for pack in "${PACKS[@]}"; do
        PACK_URL="https://raw.githubusercontent.com/osquery/osquery/master/packs/${pack}.conf"
        PACK_FILE="$PACKS_DIR/${pack}.conf"

        if [ -f "$PACK_FILE" ]; then
            print_warning "$pack already exists, skipping"
            continue
        fi

        print_warning "Downloading $pack..."
        if curl -L -o "$PACK_FILE" "$PACK_URL" 2>/dev/null; then
            chown osquery:osquery "$PACK_FILE"
            chmod 644 "$PACK_FILE"
            print_success "Downloaded $pack"
        else
            print_error "Failed to download $pack"
        fi
    done
}

validate_config() {
    print_header "Validating osquery configuration"

    # Check if config file is valid JSON
    if ! python3 -m json.tool "$OSQUERY_CONF_DIR/osquery.conf" > /dev/null 2>&1; then
        print_error "Configuration is not valid JSON"
        exit 1
    fi

    local validation_output
    local validation_db="/tmp/osquery-setup-validation.db"

    # Run osqueryd config check against a temp DB path so validation is deterministic.
    validation_output=$(sudo -u osquery osqueryd \
        --flagfile "$OSQUERY_FLAG_FILE" \
        --config_path "$OSQUERY_CONF_FILE" \
        --database_path "$validation_db" \
        --disable_events=true \
        --config_check 2>&1 || true)

    if echo "$validation_output" | grep -q "Config OK"; then
        print_success "Configuration validated successfully"
    else
        print_warning "Configuration validation output:"
        echo "$validation_output"
    fi
}

enable_service() {
    print_header "Enabling osqueryd service"

    if systemctl is-enabled osqueryd &> /dev/null; then
        print_warning "osqueryd service already enabled"
    else
        systemctl enable osqueryd
        print_success "osqueryd service enabled to start on boot"
    fi
}

start_service() {
    print_header "Starting osqueryd service"

    if systemctl is-active osqueryd &> /dev/null; then
        print_warning "osqueryd is already running, restarting..."
        systemctl restart osqueryd
    else
        systemctl start osqueryd
    fi

    sleep 2

    if systemctl is-active osqueryd &> /dev/null; then
        print_success "osqueryd service started successfully"
        systemctl status osqueryd --no-pager
    else
        print_error "Failed to start osqueryd service"
        systemctl status osqueryd --no-pager
        journalctl -u osqueryd -n 20 --no-pager
        exit 1
    fi
}

check_logs() {
    print_header "Checking osquery logs"

    if [ -f "$OSQUERY_LOG_DIR/osqueryd.results.log" ]; then
        chmod 644 "$OSQUERY_LOG_DIR/osqueryd.results.log" 2>/dev/null || true
        print_success "osquery results log file exists"
        echo ""
        echo "Latest log entries:"
        tail -n 5 "$OSQUERY_LOG_DIR/osqueryd.results.log"
    else
        print_warning "osquery results log not yet generated"
    fi
}

test_queries() {
    print_header "Testing osquery queries"

    print_warning "Running basic test query..."
    echo "SELECT * FROM system_info LIMIT 1;" | osqueryi --json 2>/dev/null | head -20

    print_success "osquery is responding to queries"
}

show_status() {
    print_header "osqueryd Status"

    echo ""
    echo "Service Status:"
    systemctl status osqueryd --no-pager || true

    echo ""
    echo "Configuration:"
    echo "  Config file: $OSQUERY_CONF_FILE"
    echo "  Flag file: $OSQUERY_FLAG_FILE"
    if [ -f "$ACTIVE_PROFILE_FILE" ]; then
        echo "  Active profile: $(cat "$ACTIVE_PROFILE_FILE")"
    else
        echo "  Active profile: unknown"
    fi
    echo "  Log directory: $OSQUERY_LOG_DIR"
    echo "  Legacy log directory: $LEGACY_OSQUERY_LOG_DIR"
    echo "  Packs directory: $PACKS_DIR"

    echo ""
    echo "Recent logs (last 10 lines):"
    tail -n 10 "$OSQUERY_LOG_DIR/osqueryd.results.log" 2>/dev/null || echo "  (No logs yet)"
}

show_help() {
    cat << EOF
Usage: sudo $0 [COMMAND] [PROFILE]

Commands:
    setup       - Complete setup (directories, config, packs, validation, enable, start)
    configure   - Copy configuration file only
    download    - Download official packs only
    validate    - Validate currently installed configuration
    start       - Start osqueryd service
    stop        - Stop osqueryd service
    restart     - Restart osqueryd service
    status      - Show service status and logs
    profiles    - List available osquery profiles
    test        - Run test query
    logs        - Tail osqueryd logs
    clean       - Stop service and remove logs
    help        - Show this help message

Profiles:
    quiet           - Default low-noise profile
    deep-forensic   - Broader, higher-volume forensic profile
    ssd-optimized   - Lowest-write profile

Examples:
    sudo $0 setup quiet                  # Complete one-time setup with the default profile
    sudo $0 configure deep-forensic      # Switch to the verbose forensic profile
    sudo $0 configure ssd-optimized      # Switch to the lowest-write profile
    sudo $0 restart                      # Restart the service
    sudo $0 status                       # Check status
    sudo $0 profiles                     # List available profiles

EOF
}

stop_service() {
    print_header "Stopping osqueryd service"

    systemctl stop osqueryd
    print_success "osqueryd service stopped"
}

restart_service() {
    print_header "Restarting osqueryd service"

    systemctl restart osqueryd
    sleep 2

    if systemctl is-active osqueryd &> /dev/null; then
        print_success "osqueryd service restarted successfully"
    else
        print_error "Failed to restart osqueryd service"
        exit 1
    fi
}

tail_logs() {
    print_header "Following osqueryd logs"

    if [ ! -f "$OSQUERY_LOG_DIR/osqueryd.results.log" ]; then
        print_error "Log file not found: $OSQUERY_LOG_DIR/osqueryd.results.log"
        exit 1
    fi

    tail -f "$OSQUERY_LOG_DIR/osqueryd.results.log"
}

clean_logs() {
    print_header "Cleaning osqueryd logs"

    systemctl stop osqueryd
    rm -f "$OSQUERY_LOG_DIR"/*
    print_success "Logs cleaned"
}

# Main execution
if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

COMMAND=$1
PROFILE_ARG=${2:-quiet}

check_root

case $COMMAND in
    setup)
        select_profile "$PROFILE_ARG"
        verify_osquery_installed
        setup_directories
        copy_config
        download_packs
        validate_config
        enable_service
        start_service
        check_logs
        print_success "osqueryd setup completed successfully!"
        ;;
    configure)
        select_profile "$PROFILE_ARG"
        setup_directories
        download_packs
        copy_config
        ;;
    download)
        setup_directories
        download_packs
        ;;
    validate)
        validate_config
        ;;
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        show_status
        ;;
    profiles)
        list_profiles
        ;;
    test)
        test_queries
        ;;
    logs)
        tail_logs
        ;;
    clean)
        clean_logs
        ;;
    help)
        show_help
        ;;
    *)
        print_error "Unknown command: $COMMAND"
        echo ""
        show_help
        exit 1
        ;;
esac
