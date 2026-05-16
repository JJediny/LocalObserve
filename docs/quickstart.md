## QUICKSTART_GUIDE.md

# Quick Start Guide 

**Status:** Your monitoring stack is fully operational!

---

## 5-Minute Setup

### 1. Access Grafana
Open your browser to:
```
http://localhost:3000
```

**Login:** admin / admin

### 2. Query Your Logs
1. Click **Explore** (left sidebar)
2. Make sure **Loki** is selected as the data source
3. In the query box, enter:
   ```
   {job="osquery"}
   ```
4. Click **Run Query** (or press Shift+Enter)

You should see osquery events logged to Loki!

### 3. View Sample Data
Common queries to try:

**See all logged-in users:**
```
{job="osquery", name="logged_in_users"}
```

**See processes:**
```
{job="osquery", name="processes"}
```

**See system info:**
```
{job="osquery", name="system_info"}
```

---

## Service Status

Check if everything is running:

```bash
cd /home/john/loki

# Docker services
docker-compose ps

# osqueryd daemon
systemctl status osqueryd

# Logs
docker-compose logs alloy     # Log collector
docker-compose logs grafana   # Web UI
```

---

## Where Are My Logs?

### osquery Results
```
/var/log/osquery/osqueryd.results.log
```
(Raw JSON format, collected by Alloy)

### Loki Storage
```
/home/john/loki/.data/
```
(S3-compatible MinIO storage)

---

## Common Tasks

### Change Grafana Password
1. Go to http://localhost:3000/admin/users
2. Click the **admin** user
3. Enter new password and save

### Stop Everything
```bash
cd /home/john/loki
docker-compose down
```

### Start Everything
```bash
cd /home/john/loki
docker-compose up -d
```

### View Real-Time Logs
```bash
# Alloy collecting logs
docker-compose logs alloy -f

# Grafana
docker-compose logs grafana -f

# osqueryd on host
sudo journalctl -u osqueryd -f
```

### Check Disk Usage
```bash
# osquery logs
du -sh /var/log/osquery/

# Loki storage
du -sh /home/john/loki/.data/
```

---

## Need Help?

See **DEPLOYMENT_COMPLETE.md** for:
- Full troubleshooting guide
- Architecture diagram
- Performance tuning tips
- Configuration reference

---

**Start monitoring now!** Open http://localhost:3000 in your browser.


## QUICKSTART.md

#  Quick Start Guide

Get your Loki log streaming stack running in minutes.

## Step 1: Verify Prerequisites

```bash
# Check Docker is installed
docker --version
# Expected: Docker version 20.10+

# Check Docker Compose is installed
docker-compose --version
# Expected: Docker Compose version 1.29+
```

## Step 2: Launch the Stack

```bash
cd /home/john/loki

# Make script executable (first time only)
chmod +x start-loki.sh

# Start everything
./start-loki.sh start
```

The script will:
-  Check prerequisites
-  Create directories
-  Generate credentials in `.env`
-  Pull Docker images
-  Start all services
-  Display URLs and status

For host osquery setup, the default profile is the quieter `quiet` mode:

- `sudo ./setup-osqueryd.sh configure quiet`
- `sudo systemctl restart osqueryd`

If you need a temporary higher-volume investigation profile instead:

- `sudo ./setup-osqueryd.sh configure deep-forensic`
- `sudo systemctl restart osqueryd`

## Step 3: Access Services

After startup (takes ~60 seconds), open in your browser:

###  Main Interface - Grafana
- **URL**: http://localhost:3000
- **Username**: `admin`
- **Password**: `admin`
- **What**: Log exploration, dashboards, queries

###  Log Storage - Loki
- **URL**: http://localhost:3100
- **Tenant**: `tenant1`
- **What**: Central log database

###  Log Collector - Alloy
- **URL**: http://localhost:12345
- **What**: Configuration, health status

###  Security - Falcosidekick
- **URL**: http://localhost:2801
- **What**: Security events from Falco

###  Object Storage - MinIO
- **URL**: http://localhost:9000
- **Username**: `loki`
- **Password**: `supersecret`
- **What**: Stores logs in S3-compatible format

## Step 4: Explore Logs in Grafana

1. Open http://localhost:3000
2. Click **Explore** (left menu)
3. Make sure **Loki** is selected in the data source dropdown
4. Try a simple query: `{job!=""}`
5. Click **Run query** to see logs

### First Queries to Try

```
# See all logs from all sources
{job!=""}

# Just system logs
{job="journald"}

# Just errors
{job="journald", level="error"}

# Docker container logs
{job="docker"}

# Security events
{job="falco"}
```

## Step 5: Common Commands

```bash
# Check status
./start-loki.sh status

# View live logs
./start-loki.sh logs

# Restart everything
./start-loki.sh restart

# Stop everything
./start-loki.sh stop

# Start again
./start-loki.sh start
```

##  What's Collecting Logs?

All of these are automatically capturing logs and sending to Loki:

| Source | Label | Location | Status |
|--------|-------|----------|--------|
| **Journald** | `job=journald` | System journal |  Auto |
| **Syslog** | `job=syslog` | Port 514 |  Auto |
| **Systemd** | `job=systemd` | Unit logs |  Auto |
| **OSQuery** | `job=osquery` | `/var/log/osquery` |  If running |
| **Falco** | `job=falco` | Docker container |  Auto |
| **Docker** | `job=docker` | Container logs |  Auto |

##  Most Common Tasks

### View recent errors
```
1. Go to http://localhost:3000/explore
2. Query: {level="error"}
3. Click "Run query"
```

### Check a specific service
```
1. Query: {job="journald", unit="docker.service"}
2. Or: {job="syslog", app="nginx"}
```

### See what happened in last hour
```
1. In Grafana, set time range to "Last 1 hour"
2. Query: {job!=""}
3. All logs from last hour appear
```

### Export logs
```bash
# Via curl
curl "http://localhost:3100/loki/api/v1/query_range?query={job=\"journald\"}&limit=1000" | jq . > logs.json
```

##  Troubleshooting

### Services aren't starting?
```bash
# Check Docker is running
docker ps

# View error logs
./start-loki.sh logs

# Restart everything
./start-loki.sh restart
```

### No logs in Grafana?
```bash
# Check Alloy is running
docker-compose ps alloy

# Check for errors
docker-compose logs alloy

# Verify Loki is accessible
curl http://localhost:3100/ready
```

### Can't access Grafana?
```bash
# Check it's running
docker-compose ps grafana

# Check port 3000 is free
netstat -tln | grep 3000

# Restart Grafana
docker-compose restart grafana
```

##  Documentation

- **Full Setup Guide**: Read `README.md`
- **Log Sources Details**: Read `LOG_SOURCES_GUIDE.md`
- **Commands Reference**: Read `COMMANDS_REFERENCE.md`
- **Architecture**: See section below

##  Architecture Overview

```

                    Your Computer                          

                                                            
         
    Journald        Syslog         Systemd       
   (System)        (Port 514)      (Units)       
         
                                                       
         
    OSQuery         Falco          Docker        
   (/var/log)     (Security)      (Containers)   
         
                                                       

                                            
          
                            
        
                  ALLOY (Log Collector)         
            Collects from all sources above     
                 - Filters                      
                 - Transforms                   
                 - Enriches with labels         
        
                            
        
                LOKI (Log Storage)              
          - Read/Write separated for scaling    
          - Uses MinIO for S3 storage           
          - Memberlist for clustering           
        
                            
        
           GRAFANA (Visualization & Querying)   
             - Pre-configured Loki datasource   
             - Explore logs                     
             - Create dashboards                
             - Set alerts                       
        
```

##  Default Credentials

Store these safely or change them after first login:

```
Grafana
  User: admin
  Pass: admin
  URL:  http://localhost:3000

MinIO
  User: loki
  Pass: supersecret
  URL:  http://localhost:9000

Loki
  Tenant: tenant1
  URL:    http://localhost:3100
```

##  When Done

Stop everything:
```bash
./start-loki.sh stop
```

Or restart:
```bash
./start-loki.sh restart
```

##  Need Help?

1. **Check docs**: `README.md`, `LOG_SOURCES_GUIDE.md`
2. **View logs**: `./start-loki.sh logs`
3. **Check status**: `./start-loki.sh status`
4. **Restart**: `./start-loki.sh restart`


## START_HERE.md

#  START HERE

Welcome! This is your quick orientation guide for the Grafana Loki + Alloy + osquery + Falco monitoring stack.

## What You Have

A complete, integrated monitoring system that combines:
- **Real-time threat detection** via Falco
- **State-based host monitoring** via osquery  
- **Centralized log aggregation** via Loki
- **Log visualization** via Grafana
- **Automated log collection** via Alloy

## Quick Start (5 Minutes)

### 1. Set up osqueryd (host monitoring)
```bash
sudo /home/john/loki/setup-osqueryd.sh setup
```

### 2. Start the Loki stack (Grafana, Loki, Alloy, etc.)
```bash
cd /home/john/loki
./start-loki.sh start
```

### 3. Access Grafana
Open http://localhost:3000
- Username: `admin`
- Password: `admin`

### 4. Query logs
- Click "Explore" (left sidebar)
- Select "Loki" datasource
- Try: `{job="osquery"}` or `{job="falco"}`

## What's Running

```
Your Host
 osqueryd (systemd service)  Monitors host state  Logs to /var/log/osquery
 Falco (container)  Detects threats  Sends alerts
 System logs (journal, syslog, docker)
         
      Alloy (container)  Collects all logs
         
      Nginx Gateway  Routes API requests
         
      Loki  Aggregates & indexes logs
         
      MinIO  Stores data
         
      Grafana  Visualize & explore
```

## Key Files

| File | Purpose |
|------|---------|
| `setup-osqueryd.sh` | Automated osqueryd setup |
| `start-loki.sh` | Manages Docker stack |
| `docker-compose.yaml` | Docker services definition |
| `osqueryd.conf` | osquery monitoring config |
| `DOCUMENTATION_INDEX.md` | Complete documentation guide |
| `DEPLOYMENT_CHECKLIST.md` | Full deployment steps |
| `OSQUERYD_TROUBLESHOOTING.md` | Error resolution |

## Common Commands

```bash
# osqueryd management
sudo systemctl status osqueryd
sudo systemctl restart osqueryd
sudo tail -f /var/log/osquery/osqueryd.results.log

# Loki stack management
cd /home/john/loki
./start-loki.sh status
./start-loki.sh stop
./start-loki.sh restart
docker-compose ps

# Test osquery
osqueryi
> SELECT * FROM system_info;
> .quit
```

## Troubleshooting

### osqueryd won't start
See `OSQUERYD_TROUBLESHOOTING.md` - look for the error in the first section

### Loki stack won't start
Run `docker-compose ps` to see which services failed, then:
```bash
docker-compose logs <service_name>
```

### No logs in Grafana
1. Verify osqueryd is running: `sudo systemctl status osqueryd`
2. Verify Loki is running: `docker-compose ps | grep loki`
3. Check logs are being collected: `sudo tail -20 /var/log/osquery/osqueryd.results.log`

### Can't connect to services
Check ports are available:
```bash
sudo netstat -tlnp | grep -E "3000|3100|12345|514"
```

## Documentation

- **[DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md)** - Complete navigation guide
- **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** - Full deployment steps
- **[README.md](README.md)** - Architecture and overview
- **[OSQUERYD_QUICK_START.md](OSQUERYD_QUICK_START.md)** - osqueryd details
- **[OSQUERYD_TROUBLESHOOTING.md](OSQUERYD_TROUBLESHOOTING.md)** - Error fixes
- **[OSQUERY_QUICK_REFERENCE.md](OSQUERY_QUICK_REFERENCE.md)** - Query examples

## What's Being Monitored

osqueryd is collecting:
-  System info & OS version
-  Cron jobs & systemd services (persistence)
-  SUID binaries & sudoers (privilege escalation)
-  Rootkit artifacts & hidden processes
-  Network ports & connections
-  Critical file changes
-  Process info & memory maps
-  User accounts & SSH keys
-  Kernel modules
-  Docker containers
-  And 30+ more security-focused queries

Falco is detecting:
-  Unauthorized file access
-  Suspicious process execution
-  Privilege escalation attempts
-  Network anomalies
-  And 100+ default detection rules

##  Important

- **Change default credentials** before using in production:
  - Grafana: admin/admin  ??? 
  - MinIO: loki/supersecret  ???
  
- **Monitor resources**: osqueryd uses ~1% CPU, Docker stack uses ~300MB RAM
- **Disk space**: Monitor `/var/log/osquery/` and `/home/john/loki/.data/`
- **Updates**: Keep osquery packs and Falco rules current

## Need Help?

### For setup issues
 Run the setup script with verbose output: `sudo bash -x setup-osqueryd.sh setup`

### For query help
 See `OSQUERY_QUICK_REFERENCE.md` for common queries

### For architecture questions
 Read `README.md` for complete architecture overview

### For error messages
 Check `OSQUERYD_TROUBLESHOOTING.md` - most errors are documented

### For everything else
 Check `DOCUMENTATION_INDEX.md` for the right document

---

**Ready to monitor? Start with Step 1 above! **

Next: [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md) or [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)


## README.md

# Lightweight Local Linux Monitoring Stack

This repository packages an extremely lightweight local Linux monitoring setup for active inspection of a host with a strong bias toward low disk-write overhead and ad hoc Docker-based analysis.

The current stack focuses on:

- local log and security event collection
- low write amplification on the host
- fast, disposable Docker startup for inspection and evaluation
- simple side-by-side comparison between a Loki-based stack and an OpenObserve-based stack
- practical host telemetry from osquery and Falco

This project is intended for local evaluation, incident triage, security experimentation, and workstation or lab monitoring. It is not positioned as a production-ready observability platform in its current form.

## What this repository provides

### Primary stack

- Grafana for querying and dashboards
- Loki for log storage and query
- Alloy for lightweight forwarding into Loki
- Falco for runtime security detection
- Falcosidekick for shipping Falco alerts into Loki
- MinIO as the local object store for Loki
- Nginx as the Loki gateway

### Comparison stack

- OpenObserve
- OpenTelemetry Collector Contrib

### Current monitored sources

The currently wired and validated sources in this repository are:

- osquery results written to the repo-local path `./.data/osquery/osqueryd.results.log`
- Falco alerts shipped through Falcosidekick into Loki
- new osquery and Falco logs mirrored into OpenObserve when you start the OpenObserve profile
- optional OTLP log ingestion into OpenObserve through the OpenTelemetry Collector profile
- on-demand host log imports staged through `./.data/host-import/inbox` with parser-aware handling for syslog-style, dpkg-style, and JSON logs

The default osquery profile is intentionally tuned to reduce noisy desktop churn. It now favors suspicious subsets and bounded inventories over full process memory maps, full process environments, and always-on pack-based duplication.

Additional source ideas and planned expansion areas are documented in `LOG_SOURCE_EXPANSION.md`.

## Design goals

This repository exists to support a specific operating style:

- keep host-side writes intentionally small and predictable
- avoid always-on heavyweight monitoring agents where possible
- make it easy to spin up Docker only when you want to inspect or evaluate something
- keep local troubleshooting understandable with plain configuration files and shell scripts
- preserve a clean path for comparing Loki/Grafana against OpenObserve/OTel Collector without replacing the main stack immediately

A longer explanation of the approach is documented in `EXPLAINER.md`.

## Quick start

### 1. Prepare the repo-local data directories

Run:

- `./start-loki.sh start`

This script checks Docker, creates the local data directories, prepares a local `.env`, starts the stack, and prints the currently exposed service URLs.

### 2. Configure osquery on the host

To point the host daemon at the repo-local log path and install the matching flagfile:

- `sudo ./setup-osqueryd.sh configure`
- `sudo systemctl restart osqueryd`

This installs the default low-noise `quiet` profile.

If you need fuller process, package, and incident-response visibility for a temporary investigation, switch to the opt-in deep forensic profile:

- `sudo ./setup-osqueryd.sh configure deep-forensic`
- `sudo systemctl restart osqueryd`

Profile details are documented in `OSQUERY_PROFILES.md`.

### 3. Open the primary interfaces

- Grafana: `http://localhost:3000`
- Loki gateway: `http://localhost:3100`
- MinIO API: `http://localhost:9000`
- MinIO console: `http://localhost:9001`

### 4. Optional comparison profile

To start the OpenObserve comparison stack with automated osquery and Falco forwarding:

- `./start-loki.sh openobserve`

Then open:

- OpenObserve: `http://localhost:5080`
- Login: `root@example.com` / `Complexpass#123`
- Note: the OpenObserve file-tail pipelines ingest new log lines after the profile starts

## Repository structure

### Core runtime files

- `docker-compose.yaml`  stack definition
- `loki-config.yaml`  Loki configuration
- `alloy-local-config.yaml`  Alloy pipeline configuration
- `falco-config.yaml`  Falco local overrides
- `falco_rules.local.yaml`  local Falco tuning and custom rules
- `otel-collector-config.yaml`  OpenTelemetry Collector config for OpenObserve comparison

### Host integration files

- `osqueryd.conf`  default low-noise osquery profile
- `osqueryd-deep-forensic.conf`  broader high-volume forensic osquery profile
- `osqueryd-ssd-optimized.conf`  lower-write osquery profile
- `osquery.flags`  CLI-only osquery daemon flags
- `setup-osqueryd.sh`  host setup helper for osquery profile installation and switching
- `osqueryi-local.sh`  interactive osquery wrapper for local use without daemon logger conflicts
- `start-loki.sh`  local startup helper for the stack

### Primary documentation

- `DOCUMENTATION_INDEX.md`  documentation map and audience guide
- `QUICKSTART.md`  fastest path to a working local setup
- `EXPLAINER.md`  project philosophy and operating model
- `DISK_OPTIMIZATION.md`  disk-write and noise-reduction decisions
- `PROJECT_PLAN.md`  planned improvements and roadmap
- `BENCHMARK_CHECKLIST.md`  benchmark execution checklist
- `BENCHMARK_CRITERIA.md`  benchmark scoring and evaluation criteria
- `LOG_SOURCE_EXPANSION.md`  recommended additional log sources
- `HOST_LOG_IMPORTS.md`  efficient on-demand staging and import of legacy host logs
- `OSQUERY_PROFILES.md`  quiet vs deep forensic vs SSD-optimized osquery profile guidance
- `STACK_EVAL_NOTES.md`  current validated state and known blockers
- `CISA_KEV_COVERAGE.md`  behavior-based Falco and osquery coverage notes for Linux KEV-style exploit monitoring

## Security and scope notes

### Current security posture

This repo is optimized for local use and evaluation.

You should assume the following before publishing or wider reuse:

- default credentials are for local use only and should be changed
- the repository currently contains local evaluation assumptions and workstation-oriented tradeoffs
- Falco coverage on Docker Desktop or LinuxKit-style environments remains only partially validated
- interactive `osqueryi` use should go through the repo wrapper if you want a clean local shell experience

### Open-source preparation status

This repository now includes:

- a cleaned-up README
- a documentation index that separates canonical docs from historical notes
- a project plan
- benchmark criteria and checklist documents
- a log source expansion plan
- a repo `.gitignore` for generated data and local credentials
- contributor and security policy stubs

Before a public release, you should still decide on:

- a license
- versioning and release policy
- support boundaries
- how much of the historical deployment/status documentation should remain in-tree

## Known limitations

- the primary validated ingest sources today are osquery and Falco, not a full host-wide log inventory
- Falco syscall-level validation is environment-limited on the current Docker Desktop/LinuxKit-style host
- Grafana live-tail behavior is still a known evaluation caveat in this repo
- the OpenObserve profile mirrors Falco through Falco file output plus OTel file tailing, rather than a direct Falcosidekick delivery path

## Documentation map

Start with:

- `DOCUMENTATION_INDEX.md`
- `QUICKSTART.md`
- `EXPLAINER.md`

Then use:

- `DISK_OPTIMIZATION.md` for low-write design context
- `PROJECT_PLAN.md` for likely next improvements
- `BENCHMARK_CHECKLIST.md` and `BENCHMARK_CRITERIA.md` for stack comparison work
- `LOG_SOURCE_EXPANSION.md` for broader monitoring coverage planning

## Validation and tests

This repository includes a small `pytest` suite for Falco and osquery configuration validation.

Use `uv` to install the test dependencies and run the checks:

- `uv sync`
- `uv run pytest`

If the Docker stack is already running and you want live ingestion checks too, run:

- `uv run pytest --run-stack -m integration`

The tests validate:

- `falco-config.yaml`
- `falco_rules.local.yaml`
- `osqueryd.conf`
- `osqueryd-ssd-optimized.conf`
- `osquery.flags`

These tests are intended to catch structural mistakes and rule/config regressions quickly before you restart services on the host.

The optional live-stack integration tests verify:

- Loki query availability
- existing osquery visibility in Loki and OpenObserve
- synthetic Falcosidekick-to-Loki delivery
- OTel Collector discovery of the Falco event file

They complement, but do not replace, native validators such as:

- `osqueryd --config_check`
- Falco startup validation through `docker compose restart falco` and `docker compose logs falco`

## Contributing and security reporting

- `CONTRIBUTING.md`
- `SECURITY.md`
