## COMMANDS_REFERENCE.md

#!/bin/bash
# Loki Stack Utility Commands Reference
# Common debugging and management commands

## ============================================
## ============================================

# Check all services status
docker-compose ps

# Check specific service
docker-compose ps alloy

# View real-time logs from all services
docker-compose logs -f

# View logs from specific service
docker-compose logs -f alloy
docker-compose logs -f loki
docker-compose logs -f grafana
docker-compose logs -f falco
docker-compose logs -f falcosidekick

# View last 50 lines from a service
docker-compose logs -f --tail 50 alloy

# Get detailed service information
docker-compose ps -a

## ============================================
## HEALTH CHECKS
## ============================================

# Check Loki health
curl http://localhost:3100/ready

# Check Alloy health
curl http://localhost:12345/api/v1/status/config

# Check Grafana health
curl http://localhost:3000/api/health

# Check Falcosidekick health
curl http://localhost:2801/health

# Check MinIO health
curl http://localhost:9000/minio/health/live

## ============================================
## LOG SOURCE VERIFICATION
## ============================================

# Verify journald is accessible
docker-compose exec alloy journalctl -n 10

# Check if syslog is working (test)
echo "Test syslog message" | nc -w 1 -u localhost 514

# View OSQuery logs
tail -f /var/log/osquery/osqueryd.results.log

# Check Falco events
docker-compose logs falco | grep "event"

# View container logs
docker-compose exec falco tail -f /var/log/falco.log

## ============================================
## CONFIGURATION VALIDATION
## ============================================

# Check docker-compose syntax
docker-compose config

# Validate Alloy configuration
curl http://localhost:12345/api/v1/status/config | jq .

# Check Loki configuration
curl http://localhost:3100/config | jq .

## ============================================
## SERVICES MANAGEMENT
## ============================================

# Start services
docker-compose up -d

# Stop services
docker-compose down

# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart alloy
docker-compose restart loki

# Rebuild images (if config changed)
docker-compose build

# Pull latest images
docker-compose pull

# Remove everything including volumes (WARNING: deletes data)
docker-compose down -v

# Scale services (if applicable)
docker-compose up -d --scale backend=2

## ============================================
## DATA INSPECTION
## ============================================

# Query Loki API for recent logs
curl "http://localhost:3100/loki/api/v1/query_range?query={job=\"journald\"}&limit=100" | jq .

# Export logs to JSON
curl "http://localhost:3100/loki/api/v1/query?query={job=\"journald\"}" | jq . > logs_export.json

# List available labels
curl "http://localhost:3100/loki/api/v1/labels" | jq .

# List label values
curl "http://localhost:3100/loki/api/v1/label/job/values" | jq .

# Check MinIO buckets
docker-compose exec minio mc ls localhost/loki-data

# View MinIO object store contents
docker-compose exec minio mc ls localhost/

## ============================================
## PERFORMANCE MONITORING
## ============================================

# Check resource usage
docker stats

# Check specific service resource usage
docker stats alloy

# View Loki ingestion rate (via metrics)
curl http://localhost:3100/metrics | grep loki_distributor_lines_received

# Check Alloy metrics
curl http://localhost:12345/metrics | grep alloy

## ============================================
## DEBUGGING
## ============================================

# Enter Alloy container shell
docker-compose exec alloy sh

# Enter Loki container shell
docker-compose exec read sh
docker-compose exec write sh

# Test syslog connectivity
docker-compose exec -T minio echo "test" | nc -w 1 -u localhost 514

# Check network connectivity between services
docker-compose exec alloy ping gateway

# View environment variables in a service
docker-compose exec alloy env | grep -i loki

# Check file permissions in container
docker-compose exec alloy ls -la /var/log/journal/

## ============================================
## CLEANUP AND MAINTENANCE
## ============================================

# Remove unused Docker images
docker image prune

# Remove unused volumes
docker volume prune

# Clean MinIO storage (careful!)
docker-compose exec minio mc rm --recursive localhost/loki-data/*

# Clean up old logs (manual)
rm -rf .data/minio/data/*

# Recreate volumes
docker-compose down -v
docker-compose up -d

## ============================================
## QUERY EXAMPLES
## ============================================

# Query all journald logs
# {job="journald"}

# Query errors only
# {job="journald", level="error"}

# Query Falco events
# {job="falco"}

# Query syslog from nginx
# {job="syslog", app="nginx"}

# Query systemd service logs
# {job="systemd", unit="docker.service"}

# Query Docker container
# {job="docker", container="my-container"}

# Query OSQuery results
# {job="osquery"}

# Rate of errors (5-minute window)
# rate({level="error"}[5m])

# Count of logs by service
# count(rate({job="syslog"}[5m])) by (app)

## ============================================
## CREDENTIAL REFERENCE
## ============================================

# Grafana
# URL: http://localhost:3000
# User: admin
# Password: admin

# Loki
# URL: http://localhost:3100
# Tenant: tenant1

# MinIO
# URL: http://localhost:9000
# User: loki
# Password: supersecret

# Alloy
# URL: http://localhost:12345

# Falcosidekick
# URL: http://localhost:2801

## ============================================
## COMMON PROBLEMS
## ============================================

# Problem: No logs appearing in Grafana
# Solution: 
# 1. Check Alloy is running: docker-compose ps alloy
# 2. Check log source: docker-compose logs alloy
# 3. Verify Loki can be reached: curl http://localhost:3100/ready
# 4. Check datasource in Grafana is pointing to correct URL

# Problem: High disk usage
# Solution:
# 1. Check MinIO size: du -sh .data/minio/
# 2. Reduce retention in loki-config.yaml
# 3. Stop services: docker-compose down
# 4. Clean data: rm -rf .data/

# Problem: Services won't start
# Solution:
# 1. Check Docker is running: sudo systemctl status docker
# 2. Pull images: docker-compose pull
# 3. Check syntax: docker-compose config
# 4. View errors: docker-compose logs

# Problem: Can't access Grafana
# Solution:
# 1. Check port 3000 is available: netstat -tln | grep 3000
# 2. Check service is running: docker-compose ps grafana
# 3. Try accessing: curl http://localhost:3000/
# 4. Check logs: docker-compose logs grafana

# Problem: Falco not collecting events
# Solution:
# 1. Check Falco container: docker-compose ps falco
# 2. Check Falcosidekick: docker-compose logs falcosidekick
# 3. Test connectivity: curl http://localhost:2801/health
# 4. Check network between containers: docker-compose exec alloy ping falcosidekick

## ============================================
## USEFUL SHORTCUTS
## ============================================

# Watch logs in real-time
# alias wlog='docker-compose logs -f'

# Quick status check
# alias lstatus='docker-compose ps'

# Quick restart
# alias lrestart='docker-compose restart'

# Clean restart (stop + remove volumes + start)
# alias lclean='docker-compose down -v && docker-compose up -d'

# Export these to ~/.bashrc or ~/.zshrc for permanent use
