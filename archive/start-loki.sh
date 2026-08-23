#!/bin/bash
# Loki Stack Setup and Launch Script
# Automated setup for Grafana Loki, Alloy, Falco, and Falcosidekick

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DOCKER_COMPOSE_FILE="docker-compose.yaml"
ALLOY_CONFIG="alloy-local-config.yaml"
LOKI_CONFIG="loki-config.yaml"
FALCO_CONFIG="falco-config.yaml"
ENABLE_OPENOBSERVE_PROFILE=0

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}Loki Log Streaming Stack Setup${NC}"
echo -e "${BLUE}================================================${NC}"

# Check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}✗ Docker is not installed${NC}"
        echo "Please install Docker from https://docs.docker.com/get-docker/"
        exit 1
    fi
    echo -e "${GREEN}✓ Docker is installed${NC}"
}

# Check if Docker Compose is installed
check_docker_compose() {
    if ! docker compose version &> /dev/null; then
        echo -e "${RED}✗ Docker Compose is not installed${NC}"
        echo "Please install Docker Compose from https://docs.docker.com/compose/install/"
        exit 1
    fi
    echo -e "${GREEN}✓ Docker Compose is installed${NC}"
}

# Check if configuration files exist
check_configs() {
    local missing=0
    local configs=("$DOCKER_COMPOSE_FILE" "$ALLOY_CONFIG" "$LOKI_CONFIG" "$FALCO_CONFIG")

    if [ "$ENABLE_OPENOBSERVE_PROFILE" -eq 1 ]; then
        configs+=("otel-collector-config.yaml")
    fi

    for config in "${configs[@]}"; do
        if [ ! -f "$config" ]; then
            echo -e "${RED}✗ Missing $config${NC}"
            missing=1
        else
            echo -e "${GREEN}✓ Found $config${NC}"
        fi
    done

    if [ $missing -eq 1 ]; then
        echo -e "${RED}Some configuration files are missing!${NC}"
        exit 1
    fi
}

# Create necessary directories
create_directories() {
    mkdir -p .data/minio .data/logs .data/osquery .data/openobserve .data/falco .data/host-import/inbox
    chmod 777 .data/minio .data/logs .data/openobserve 2>/dev/null || true
    chmod 755 .data/osquery .data/falco .data/host-import .data/host-import/inbox 2>/dev/null || true
    echo -e "${GREEN}✓ Created necessary directories${NC}"
}

# Generate automated authentication credentials
setup_auth() {
    echo -e "\n${YELLOW}Setting up automated authentication...${NC}"

    # Generate per-checkout credentials instead of committing or reusing
    # development passwords in the archived launcher.
    local grafana_password minio_password zo_password
    if command -v openssl &>/dev/null; then
        grafana_password="$(openssl rand -hex 24)"
        minio_password="$(openssl rand -hex 24)"
        zo_password="$(openssl rand -hex 24)"
    else
        grafana_password="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
        minio_password="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
        zo_password="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
    fi

    cat > .env << EOF
# Loki Stack Credentials (generated for this checkout)
GRAFANA_USER=admin
GRAFANA_PASSWORD=$grafana_password
GRAFANA_ADMIN_EMAIL=admin@localhost
LOKI_TENANT_ID=tenant1
MINIO_ROOT_USER=loki
MINIO_ROOT_PASSWORD=$minio_password
ALLOY_LISTEN_ADDR=0.0.0.0:12345
ZO_ROOT_USER_EMAIL=root@example.com
ZO_ROOT_USER_PASSWORD=$zo_password
EOF

    chmod 600 .env
    echo -e "${GREEN}✓ Created .env file with generated credentials${NC}"
    echo -e "${YELLOW}Note: Credentials are stored in the local .env file${NC}"
}

# Setup osquery logging
setup_osquery() {
    echo -e "\n${YELLOW}Setting up OSQuery logging directory...${NC}"

    mkdir -p .data/osquery

    echo -e "${GREEN}✓ Repo-local OSQuery log directory ready: $SCRIPT_DIR/.data/osquery${NC}"

    if [ -f .data/osquery/osqueryd.results.log ] && [ ! -r .data/osquery/osqueryd.results.log ]; then
        echo -e "${YELLOW}⚠ Existing osqueryd.results.log is not readable by the Docker collectors yet.${NC}"
        echo -e "${YELLOW}⚠ Rerun sudo ./setup-osqueryd.sh configure && sudo systemctl restart osqueryd to apply --logger_mode=0644.${NC}"
    else
        echo -e "${YELLOW}⚠ If osqueryd is already installed, rerun sudo ./setup-osqueryd.sh configure && sudo systemctl restart osqueryd${NC}"
    fi
}

# Setup syslog forwarding
setup_syslog() {
    echo -e "\n${YELLOW}Setting up syslog forwarding...${NC}"

    # Check if rsyslog is running
    if systemctl is-active --quiet rsyslog; then
        echo -e "${GREEN}✓ rsyslog is running${NC}"
    else
        echo -e "${YELLOW}⚠ rsyslog is not running. Some system logs may not be captured.${NC}"
        echo "Consider starting it with: sudo systemctl start rsyslog"
    fi
}

# Pull Docker images
pull_images() {
    echo -e "\n${YELLOW}Pulling Docker images...${NC}"

    if [ "$ENABLE_OPENOBSERVE_PROFILE" -eq 1 ]; then
        docker compose --profile openobserve pull --quiet
    else
        docker compose pull --quiet
    fi

    echo -e "${GREEN}✓ Docker images pulled${NC}"
}

# Start services
start_services() {
    echo -e "\n${YELLOW}Starting services...${NC}"

    if [ "$ENABLE_OPENOBSERVE_PROFILE" -eq 1 ]; then
        docker compose --profile openobserve up -d
    else
        docker compose up -d
    fi

    echo -e "${GREEN}✓ Services started${NC}"
}

# Wait for services to be healthy
wait_for_services() {
    echo -e "\n${YELLOW}Waiting for services to be healthy...${NC}"

    local timeout=120
    local elapsed=0
    local loki_ready=0
    local openobserve_ready=0

    while [ $elapsed -lt $timeout ]; do
        if [ $loki_ready -eq 0 ] && curl -fsS http://localhost:3100/ready &>/dev/null; then
            echo -e "${GREEN}✓ Loki is ready${NC}"
            loki_ready=1
        fi

        if [ "$ENABLE_OPENOBSERVE_PROFILE" -eq 1 ] && [ $openobserve_ready -eq 0 ] && curl -fsS http://localhost:5080/healthz &>/dev/null; then
            echo -e "${GREEN}✓ OpenObserve is ready${NC}"
            openobserve_ready=1
        fi

        if [ $loki_ready -eq 1 ] && { [ "$ENABLE_OPENOBSERVE_PROFILE" -eq 0 ] || [ $openobserve_ready -eq 1 ]; }; then
            break
        fi

        sleep 5
        elapsed=$((elapsed + 5))
        echo "Waiting... (${elapsed}s/${timeout}s)"
    done

    if [ $elapsed -ge $timeout ]; then
        echo -e "${YELLOW}⚠ Services may still be starting up${NC}"
    fi
}

# Display service information
display_info() {
    echo -e "\n${BLUE}================================================${NC}"
    echo -e "${BLUE}Services Information${NC}"
    echo -e "${BLUE}================================================${NC}"

    echo -e "${GREEN}Grafana:${NC} http://localhost:3000"
    echo -e "  User: admin | Password: admin"

    echo -e "\n${GREEN}Alloy:${NC} http://localhost:12345"
    echo -e "  Server: http://localhost:12345"

    echo -e "\n${GREEN}Loki:${NC} http://localhost:3100"
    echo -e "  Gateway: http://localhost:3100"

    echo -e "\n${GREEN}MinIO API:${NC} http://localhost:9000"
    echo -e "${GREEN}MinIO Console:${NC} http://localhost:9001"
    echo -e "  User: loki | Password: supersecret"

    if [ "$ENABLE_OPENOBSERVE_PROFILE" -eq 1 ]; then
        echo -e "\n${GREEN}OpenObserve:${NC} http://localhost:5080"
        echo -e "  User: root@example.com | Password: Complexpass#123"
        echo -e "  Streams: osquery, falco, otlp-logs"
        echo -e "  Note: osquery and Falco file pipelines ingest new events after startup"
    else
        echo -e "\n${GREEN}Optional OpenObserve profile:${NC} ./start-loki.sh openobserve"
        echo -e "  UI: http://localhost:5080"
        echo -e "  User: root@example.com | Password: Complexpass#123"
    fi

    echo -e "\n${BLUE}Log Sources Configured:${NC}"
    echo -e "  • OSQuery ($SCRIPT_DIR/.data/osquery/osqueryd.results.log)"
    echo -e "  • Falco (via Falcosidekick → Loki and file tailing → OpenObserve)"
    echo -e "  • On-demand host log imports ($SCRIPT_DIR/.data/host-import/inbox)"
    echo -e "  • Optional OTLP logs (via the OpenObserve profile)"

    echo -e "\n${BLUE}Next Steps:${NC}"
    echo -e "  1. Open Grafana: ${GREEN}http://localhost:3000${NC}"
    echo -e "  2. The Loki datasource is pre-configured"
    echo -e "  3. Explore logs in Grafana → Explore → Logs"
    echo -e "  4. View all services: ${YELLOW}docker compose ps${NC}"
    echo -e "  5. View logs: ${YELLOW}docker compose logs -f${NC}"
    echo -e "  6. Stop services: ${YELLOW}docker compose down${NC}"

    echo -e "\n${BLUE}================================================${NC}"
}

# Main setup flow
main() {
    check_docker
    check_docker_compose
    check_configs
    create_directories
    setup_auth
    setup_osquery
    setup_syslog
    pull_images
    start_services
    wait_for_services
    display_info
}

# Parse command line arguments
case "${1:-start}" in
    start)
        main
        ;;
    openobserve)
        ENABLE_OPENOBSERVE_PROFILE=1
        main
        ;;
    stop)
        echo -e "${YELLOW}Stopping services...${NC}"
        docker compose down
        echo -e "${GREEN}✓ Services stopped${NC}"
        ;;
    restart)
        echo -e "${YELLOW}Restarting services...${NC}"
        docker compose restart
        echo -e "${GREEN}✓ Services restarted${NC}"
        ;;
    status)
        docker compose ps
        ;;
    logs)
        docker compose logs -f
        ;;
    *)
        echo "Usage: $0 {start|openobserve|stop|restart|status|logs}"
        exit 1
        ;;
esac
