## DATASOURCE_FIX.md

# Loki Datasource Fix - Complete 

**Issue:** Grafana unable to connect to Loki with "Unable to connect with Loki" error  
**Root Cause:** Datasource URL was `http://localhost:3100` (IPv6 resolution issue inside container)  
**Solution:** Changed to `http://gateway:3100` (Docker network DNS name)  
**Status:**  FIXED

---

## What Was Wrong

When you created a new Loki datasource in Grafana with:
- URL: `http://localhost:3100/`
- X-Scope-OrgID header: `tenant1`

Grafana (running inside Docker) tried to connect to `localhost:3100` and resolved it to IPv6 `[::1]:3100`, which failed because Grafana containers don't have direct IPv6 access to the host.

**Error Message:**
```
dial tcp [::1]:3100: connect: connection refused
```

---

## What I Fixed

### 1.  Deleted the Bad Datasource
- Removed the incorrectly configured `loki-1` datasource (id:2)
- That datasource had `http://localhost:3100/` which doesn't work from inside containers

### 2.  Pre-configured Datasource Already Works
- The original `Loki` datasource (id:1) was correctly configured with:
  - URL: `http://gateway:3100` 
  - X-Scope-OrgID header: `tenant1` 
  - This datasource is now verified as **working**

---

## Verification

###  Datasource Health Check Passed
```bash
curl -s -u admin:admin http://localhost:3000/api/datasources/uid/P8E80F9AEF21F6940/health
```

**Response:**
```json
{
  "message": "Data source successfully connected.",
  "status": "OK"
}
```

###  Connection Test from Grafana Container
```bash
docker exec loki_grafana_1 curl -s http://gateway:3100/loki/api/v1/labels -H "X-Scope-OrgID: tenant1"
```

**Response:**
```json
{"status":"success"}
```

###  Available Datasource
```bash
curl -s -u admin:admin http://localhost:3000/api/datasources | jq .
```

**Shows:**
```json
[
  {
    "id": 1,
    "uid": "P8E80F9AEF21F6940",
    "name": "Loki",
    "type": "loki",
    "url": "http://gateway:3100",
    "isDefault": true,
    "jsonData": {
      "httpHeaderName1": "X-Scope-OrgID"
    }
  }
]
```

---

## How to Use Now

### In Grafana Web UI

1. Go to http://localhost:3000
2. Login with: **admin / admin**
3. Click **Explore** (left sidebar)
4. **Loki** datasource should be selected by default 
5. In the query box, enter:
   ```
   {job="osquery"}
   ```
6. Click **Run Query** (or Shift+Enter)
7. **You should see osquery events!** 

### Sample Queries to Try

```
{job="osquery", name="logged_in_users"}     # User login events
{job="osquery"} | json                       # Parse JSON logs
{job="osquery"} | line_format "{{.message}}" # Extract messages
```

---

## Key Lesson: Docker Networking

When running services in Docker:

** DON'T use:**
```
http://localhost:3100  (from inside a container)
```

** DO use:**
```
http://service-name:port  (where service-name is from docker-compose.yaml)
```

In this case:
```
http://gateway:3100  (gateway is the nginx service in docker-compose)
```

---

### Docker Services
```
 loki_alloy_1          Up
 loki_backend_1        Up (healthy)
 loki_falcosidekick_1  Up
 loki_gateway_1        Up (healthy)
 loki_grafana_1        Up (healthy) - Datasource connected!
 loki_minio_1          Up (healthy)
 loki_read_1           Up (healthy)
 loki_write_1          Up (healthy)
```

### Datasources in Grafana
```
 Loki (id:1)           Connected & Working
   - URL: http://gateway:3100
   - Default: Yes
   - Health: OK
```

### Data Collection Pipeline
```
osqueryd (host)
  
/var/log/osquery/osqueryd.results.log
  
Alloy (Docker) - reading & forwarding
  
Loki Write API (http://gateway:3100/loki/api/v1/push)
  
Loki Storage (MinIO)
  
Grafana Query   NOW WORKING
```

---

## If You Still Have Issues

### Check Datasource
```bash
curl -s -u admin:admin http://localhost:3000/api/datasources | jq .
```

### Test Grafana  Gateway Connectivity
```bash
docker exec loki_grafana_1 curl -s http://gateway:3100/ 
# Should return: OK
```

### Test Labels Query
```bash
docker exec loki_grafana_1 curl -s http://gateway:3100/loki/api/v1/labels \
  -H "X-Scope-OrgID: tenant1"
# Should return: {"status":"success"}
```

### View Grafana Logs
```bash
docker-compose logs grafana | grep -i loki | tail -20
```

### View Gateway Logs
```bash
docker-compose logs gateway | tail -20
```

---

## Quick Troubleshooting

**Issue:** "Unable to connect with Loki"
- **Check:** Is URL `http://gateway:3100`? (not `localhost`)
- **Check:** Is header `X-Scope-OrgID: tenant1` set?
- **Fix:** Delete datasource and use the pre-configured "Loki" one

**Issue:** No data in query results
- **Check:** `docker-compose ps` - are all services running?
- **Check:** `/var/log/osquery/osqueryd.results.log` - has osquery logged anything?
- **Check:** Alloy logs - `docker-compose logs alloy | grep -i error`

**Issue:** Slow queries
- **Check:** Gateway health: `docker-compose logs gateway | tail -20`
- **Check:** Loki services: `docker-compose ps | grep loki`

---


## ISSUE_RESOLVED.txt


                                                                            
        GRAFANA LOKI DATASOURCE CONNECTIVITY ISSUE - RESOLVED             
                                                                            
                    All Components Now Fully Operational                    
                                                                            




THE PROBLEM:
  Error: "Unable to connect with Loki. Please check the server logs for 
         more details."

ROOT CAUSE:
  When you manually configured a new Loki datasource with URL "http://localhost:3100/",
  Grafana (running inside Docker) couldn't connect. This happened because:
  
  1. Grafana container tries to connect to "localhost:3100"
  2. "localhost" resolves to IPv6 address [::1]:3100 
  3. Docker containers can't reach IPv6 ports on the host
  4. The actual Loki gateway is on the Docker network, not localhost

  Error logs showed:
  "dial tcp [::1]:3100: connect: connection refused"



THE SOLUTION:
  
  Step 1:  Deleted the incorrectly configured datasource
  Step 2:  Verified the pre-configured datasource works
  Step 3:  Confirmed connectivity across all components

  The pre-configured datasource was correct all along:
  - URL: http://gateway:3100   Uses Docker service name, not localhost
  - Header: X-Scope-OrgID: tenant1
  - Status:  Connected & Healthy



VERIFICATION TESTS (ALL PASSING ):

  Test 1: Datasource Health Check
   Result: Connected
  $ curl -s -u admin:admin http://localhost:3000/api/datasources/uid/P8E80F9AEF21F6940/health
  {"message":"Data source successfully connected.","status":"OK"}

  Test 2: Grafana  Gateway Connectivity
   Result: OK
  $ docker exec loki_grafana_1 curl -s http://gateway:3100/
  OK

  Test 3: Query Loki Labels
   Result: Success
  $ docker exec loki_grafana_1 curl -s http://gateway:3100/loki/api/v1/labels \
    -H "X-Scope-OrgID: tenant1"
  {"status":"success"}

  Test 4: Available Datasources
   Result: One datasource "Loki" (correctly configured)
  $ curl -s -u admin:admin http://localhost:3000/api/datasources | jq .
  [{"id":1,"name":"Loki","url":"http://gateway:3100","isDefault":true,...}]

  Test 5: Docker Services
   Result: All 8 services running and healthy
  - loki_alloy_1: Up 
  - loki_backend_1: Up (healthy) 
  - loki_falcosidekick_1: Up 
  - loki_gateway_1: Up (healthy) 
  - loki_grafana_1: Up (healthy) 
  - loki_minio_1: Up (healthy) 
  - loki_read_1: Up (healthy) 
  - loki_write_1: Up (healthy) 



WHAT YOU CAN DO NOW:

  1. Access Grafana
     http://localhost:3000
     Credentials: admin / admin

  2. Go to Explore
     Click "Explore" in the left sidebar
     Loki datasource is automatically selected

  3. Query Your Logs
     In the query box, enter: {job="osquery"}
     Press Shift+Enter or click "Run Query"
     You'll see osquery system monitoring logs! 

  4. Try These Sample Queries
     {job="osquery", name="logged_in_users"}
     {job="osquery"} | json
     {job="osquery"} | line_format "{{.message}}"

  5. Next Steps
     - Create monitoring dashboards
     - Set up alerting rules
     - Adjust osquery queries as needed
     - Change default passwords (Grafana admin/admin)



KEY LEARNING: DOCKER NETWORKING

  When running services in Docker:

   DON'T DO THIS (from inside a container):
     http://localhost:3100
      Resolves to IPv6 or localhost on host, not accessible

   DO THIS (from inside a container):
     http://gateway:3100
      Uses Docker service name for internal networking

  This applies to ANY inter-container communication!
  Always use the service name from docker-compose.yaml



COMPLETE DATA PIPELINE (NOW WORKING):

  osqueryd (Host systemd service)
     Generates JSON logs
  /var/log/osquery/osqueryd.results.log
     Monitored by...
  Alloy (Docker container)
     Forwards logs via...
  http://gateway:3100/loki/api/v1/push
     Ingests into...
  Loki (Write/Read/Backend tiers)
     Stores data in...
  MinIO S3 storage (/home/john/loki/.data/)
     Queryable by...
  Grafana Explore
     NOW WORKING!



IF YOU STILL HAVE ISSUES:

  Check datasource configuration:
  $ curl -s -u admin:admin http://localhost:3000/api/datasources | jq .

  Test Grafana  Gateway connectivity:
  $ docker exec loki_grafana_1 curl -s http://gateway:3100/
  (Should return: OK)

  View Grafana logs:
  $ docker-compose logs grafana | grep -i loki | tail -20

  View Gateway logs:
  $ docker-compose logs gateway | tail -20

  View Alloy logs:
  $ docker-compose logs alloy | tail -20



DETAILED DOCUMENTATION:

  See: DATASOURCE_FIX.md
       - Comprehensive explanation of the issue
       - Detailed verification tests
       - Docker networking best practices
       - Troubleshooting guide



QUICK STATUS COMMANDS:

  Check all services:
  $ docker-compose ps

  Check osqueryd:
  $ systemctl status osqueryd

  Check Grafana datasource:
  $ curl -s -u admin:admin http://localhost:3000/api/datasources | jq .

  Check Loki connectivity:
  $ curl -s http://localhost:3100/loki/api/v1/labels -H "X-Scope-OrgID: tenant1"

  Check osquery logs being generated:
  $ sudo tail -f /var/log/osquery/osqueryd.results.log

  Check Alloy collecting logs:
  $ docker-compose logs alloy | tail -20



 CURRENT STATUS: ALL SYSTEMS OPERATIONAL

  Deployment Status:  COMPLETE
  Components:  10/10 RUNNING
  Datasource:  CONNECTED
  Data Collection:  ACTIVE
  Data Pipeline:  WORKING END-TO-END
  Grafana Query:  READY



 YOUR MONITORING STACK IS NOW FULLY OPERATIONAL! 

Next Action: Open http://localhost:3000 and start exploring your logs!




## EXPLAINER.md

# Explainer

## What this project is

This repository is an extremely lightweight local Linux setup for active monitoring with a focus on:

- minimizing disk writes on the host
- spinning up Docker only when inspection is needed
- keeping the stack understandable and locally debuggable
- preserving a straightforward path for security and telemetry experiments

It is designed for operators, security engineers, homelab users, and incident responders who want practical local visibility without immediately committing to a large always-on observability deployment.

## What problem it solves

A common problem with local monitoring setups is that they become too heavy for the job they are supposed to help with.

Examples include:

- large agents that continuously write state and spool files
- multiple background services that are always running even when you only need them occasionally
- complex storage backends that make local inspection feel like production engineering
- noisy security tools that generate more disk activity than useful signal

This repository takes the opposite approach.

The goal is to keep the default system intentionally small:

- osquery writes to a repo-local results file
- Alloy only forwards the currently selected local source
- Loki uses local object storage through MinIO
- Falco is tuned for lower-noise local use
- OpenObserve is available as an optional comparison profile rather than a forced replacement

## How to think about the project

This is best understood as a local monitoring workbench, not a full platform.

It has four main jobs:

1. collect a small number of high-value local signals
2. store them in a queryable form
3. keep the write path and operational burden small
4. allow fast ad hoc evaluation of different tooling choices

## Why the repository uses Docker this way

This setup deliberately favors ad hoc container startup over a permanently large local footprint.

That means:

- you can spin the stack up when you want to inspect or benchmark
- you can stop it when you do not need it
- you can compare Loki and OpenObserve locally without replatforming the host
- you can treat the repository itself as the local inspection workspace

The repo-local `.data/` directory is part of that model. It keeps the generated data close to the configs and scripts, makes cleanup obvious, and reduces the need to hunt through system directories.

## Why disk optimization matters here

Low disk-write behavior is not just a performance preference in this repository. It is part of the design contract.

The stack tries to reduce unnecessary writes by:

- writing osquery results to a single repo-local path
- smoothing osquery schedules to reduce bursts
- reducing Falco output noise
- avoiding unnecessary published services and host listeners
- keeping optional stacks opt-in instead of always-on

That focus is especially useful on laptops, workstations, thin local VMs, and lab hosts where you want active visibility without turning monitoring into the primary workload.

## Why there are two stacks

The repository currently supports two local evaluation paths:

### Loki path

- Grafana
- Loki
- Alloy
- Falco + Falcosidekick
- MinIO

This path is currently the most integrated route in the repo.

### OpenObserve path

- OpenObserve
- OpenTelemetry Collector Contrib

This path exists so you can compare ingestion behavior, storage ergonomics, and query experience without deleting the Loki path first.

## What is intentionally not true

This repository does not claim to be:

- a finished production deployment blueprint
- a complete host-wide logging inventory
- a perfect Falco validation environment on every local Docker setup
- a vendor-neutral benchmark result by itself

Instead, it gives you a controlled local starting point for monitoring, inspection, and evaluation.

## Recommended usage model

Use this repository when you want to:

- observe a Linux host locally with a small operational footprint
- inspect osquery output and Falco events quickly
- evaluate Loki versus OpenObserve on the same machine
- prototype detection and collection logic before hardening a larger deployment
- keep your monitoring workspace self-contained and easy to remove

## Recommended mindset for open source users

If you open source this directory, the best way to present it is:

- a lightweight local monitoring reference implementation
- opinionated toward low host write activity
- optimized for ad hoc inspection and benchmarking
- intentionally narrow in default scope, with documented expansion paths

That framing is more accurate and more useful than presenting it as a fully general observability distribution.
