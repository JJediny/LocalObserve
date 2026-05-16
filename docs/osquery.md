## OSQUERYD_TROUBLESHOOTING.md

# osqueryd Troubleshooting & Error Resolution

## Common Errors and Solutions

### Error: "osqueryd Pidfile check failed: Pidfile::Error::AccessDenied"

**What it means**: osqueryd is trying to create a pidfile but doesn't have permission. This happens when running as a non-root user without the service manager.

**Solution**: Run osqueryd as a service or with sudo:

```bash
# Option 1: Run as service (recommended)
sudo systemctl start osqueryd

# Option 2: Run with sudo directly
sudo osqueryd --config_path /etc/osquery/osquery.conf

# Option 3: Run interactively for testing
osqueryi  # (shell, not daemon)
```

---

### Error: "Error reading config: config file does not exist: /etc/osquery/osquery.conf"

**What it means**: osqueryd is looking for the configuration file but it doesn't exist at the expected path.

**Solution**: Copy the configuration file:

```bash
# Option 1: Use the setup script (automated)
sudo /home/john/loki/setup-osqueryd.sh configure

# Option 2: Manual copy
sudo cp /home/john/loki/osqueryd.conf /etc/osquery/osquery.conf
sudo chown osquery:osquery /etc/osquery/osquery.conf
sudo chmod 644 /etc/osquery/osquery.conf
```

Then verify:
```bash
ls -la /etc/osquery/osquery.conf
```

---

### Error: "Event publisher not enabled: BPFEventPublisher/auditeventpublisher/inotify/syslog"

**What it means**: These are informational messages, not errors. osquery is reporting which event publishers are disabled via configuration. This is normal and expected on systems that don't have these features enabled or available.

**Solution**: No action needed - this is normal. These warnings can be safely ignored for our use case (file-based logging).

**To verify configuration is still working**:
```bash
# Wait a few seconds, then check for log files
sleep 5
ls -la /var/log/osquery/
```

---

## Pre-Setup Verification Checklist

Before running the full setup, verify your system:

```bash
# 1. Check osquery is installed
osqueryd --version

# 2. Verify osquery user exists
id osquery

# 3. Check if service is already running
sudo systemctl status osqueryd

# 4. Check existing logs
ls -la /var/log/osquery/ 2>/dev/null || echo "Log directory doesn't exist yet"

# 5. Check existing config
ls -la /etc/osquery/ 2>/dev/null || echo "Config directory doesn't exist yet"
```

---

## Step-by-Step Setup with Error Checking

### Step 1: Install osquery (if needed)

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y osquery

# CentOS/RHEL
sudo yum install -y osquery

# macOS
brew install osquery

# Verify installation
osqueryd --version
```

**If this fails**: osquery package not available for your distro. Visit https://osquery.io/downloads/

### Step 2: Run the automated setup script

```bash
sudo /home/john/loki/setup-osqueryd.sh setup
```

**Expected output**:
```
=== Verifying osquery installation ===
 osquery installed: osquery version X.Y.Z
=== Setting up directories and permissions ===
 Directory permissions set
=== Copying osquery configuration ===
 Configuration copied to /etc/osquery/osquery.conf
=== Downloading official osquery packs ===
 Downloaded incident-response
 Downloaded ossec-rootkit
 Downloaded it-compliance
=== Validating osquery configuration ===
 Configuration validated successfully
=== Enabling osqueryd service ===
 osqueryd service enabled to start on boot
=== Starting osqueryd service ===
 osqueryd service started successfully
=== Checking osquery logs ===
 osquery results log file exists
```

### Step 3: Verify service is running

```bash
sudo systemctl status osqueryd
```

**Expected output**: `active (running)`

### Step 4: Check logs

```bash
sudo tail -20 /var/log/osquery/osqueryd.results.log | head -5
```

**Expected output**: JSON-formatted query results

---

## If Setup Fails

### Debug Step 1: Check service status and errors

```bash
# Service status
sudo systemctl status osqueryd

# Recent errors
sudo journalctl -u osqueryd -n 50 --no-pager

# Full service output
sudo systemctl start osqueryd --verbose
```

### Debug Step 2: Run osqueryd manually to see errors

```bash
# This will show all output
sudo osqueryd --config_path /etc/osquery/osquery.conf --verbose --logtostderr
```

Press `Ctrl+C` after a few seconds.

### Debug Step 3: Validate configuration

```bash
# Check JSON syntax
python3 -m json.tool /etc/osquery/osquery.conf > /dev/null 2>&1 && echo " JSON is valid" || echo " JSON has errors"

# Run osqueryd config check
sudo osqueryd --config_path /etc/osquery/osquery.conf --config_check
```

### Debug Step 4: Check permissions

```bash
# Verify osquery user exists
id osquery

# Check config file permissions
ls -la /etc/osquery/osquery.conf

# Check log directory
ls -la /var/log/osquery/

# Expected:
# - osquery user should exist
# - /etc/osquery/osquery.conf should be readable by osquery
# - /var/log/osquery should be writable by osquery
```

**If permissions are wrong, fix them**:
```bash
sudo chown osquery:osquery /etc/osquery/osquery.conf
sudo chown osquery:osquery /var/log/osquery
sudo chmod 644 /etc/osquery/osquery.conf
sudo chmod 755 /var/log/osquery
```

### Debug Step 5: Check packs are accessible

```bash
# List packs
ls -la /etc/osquery/packs/

# Verify they're readable by osquery
sudo -u osquery cat /etc/osquery/packs/incident-response.conf > /dev/null 2>&1 && echo " Pack readable" || echo " Pack not readable"
```

---

## Testing After Setup

### Quick Test 1: Interactive Shell

```bash
osqueryi
SELECT hostname FROM system_info;
```

Exit with `.quit` or `Ctrl+D`

### Quick Test 2: Query Results Log

```bash
# Wait a minute for queries to run
sleep 60

# View results
sudo tail -50 /var/log/osquery/osqueryd.results.log | python3 -m json.tool | head -50
```

You should see JSON objects with query results.

### Quick Test 3: Service Management

```bash
# Stop service
sudo systemctl stop osqueryd

# Verify it stopped
sudo systemctl status osqueryd  # Should show "inactive (dead)"

# Start it again
sudo systemctl start osqueryd

# Verify it started
sudo systemctl status osqueryd  # Should show "active (running)"
```

---

## Verification Checklist

Once setup is complete, verify everything works:

- [ ] `osqueryd --version` returns version number
- [ ] `/etc/osquery/osquery.conf` exists and is readable
- [ ] `/etc/osquery/packs/*.conf` files exist
- [ ] `/var/log/osquery/` directory is writable
- [ ] `sudo systemctl status osqueryd` shows "active (running)"
- [ ] `sudo tail /var/log/osquery/osqueryd.results.log` shows JSON results
- [ ] Test query in osqueryi returns results: `SELECT * FROM system_info;`
- [ ] No errors in `sudo journalctl -u osqueryd -n 20`

---

## Quick Reference: Common Commands

```bash
# Start/stop/restart
sudo systemctl start osqueryd
sudo systemctl stop osqueryd
sudo systemctl restart osqueryd

# Run tests
osqueryi
sudo osqueryd --config_path /etc/osquery/osquery.conf --config_check

# Check permissions and files
ls -la /etc/osquery/
ls -la /var/log/osquery/
id osquery

# Setup script
sudo /home/john/loki/setup-osqueryd.sh setup   # One-time setup
sudo /home/john/loki/setup-osqueryd.sh status  # Check status
sudo /home/john/loki/setup-osqueryd.sh logs    # Follow logs
```

---

## Still Having Issues?

1. **Post the full error message**: Run `sudo /home/john/loki/setup-osqueryd.sh setup` and capture the output
2. **Check your OS**: Ubuntu/Debian/CentOS/RHEL/macOS? (affects package names)
3. **Check available disk space**: `df -h /var/log/osquery/`
4. **Check SELinux/AppArmor**: These might block osquery on some systems
5. **Check if osquery is already running**: `ps aux | grep osqueryd`

---


## OSQUERY_SETUP_GUIDE.md

# OSQuery Configuration for Linux Exploit Detection

This guide covers installing and configuring `osqueryd` to detect standard Linux exploits and rootkits, integrated with Falco and Loki for centralized logging.

##  Overview

The `osqueryd.conf` configuration provided monitors:
- **Persistence mechanisms** (cron, systemd services, SSH keys)
- **Privilege escalation vectors** (SUID binaries, kernel modules, sudoers)
- **Rootkit artifacts** (known malware files, suspicious processes)
- **Network exploitation** (listening ports, suspicious connections)
- **File system attacks** (critical file changes, library injection)
- **Memory exploitation** (process injection, code execution)
- **User/authentication attacks** (unauthorized users, SSH backdoors)
- **Container/Docker security** (container breakouts, malicious images)

##  Installation

### Ubuntu/Debian

```bash
# Add OSQuery repository
sudo curl -L https://pkg.osquery.io/linux/pubkey.gpg | apt-key add -
sudo add-apt-repository 'deb [arch=amd64] https://pkg.osquery.io/linux deb main'

# Install osquery
sudo apt-get update
sudo apt-get install -y osquery

# Verify installation
osqueryi --version
```

### RHEL/CentOS/Fedora

```bash
# Install osquery
sudo yum install -y https://pkg.osquery.io/linux/osquery-latest.linux.x86_64.rpm

# Verify installation
osqueryi --version
```

##  Configuration Setup

### 1. Create Configuration Directory

```bash
sudo mkdir -p /etc/osquery/packs
sudo mkdir -p /var/log/osquery
sudo chown -R osquery:osquery /var/log/osquery
sudo chmod 755 /var/log/osquery
```

### 2. Copy Configuration File

```bash
# Copy the osqueryd.conf to /etc/osquery/
sudo cp /home/john/loki/osqueryd.conf /etc/osquery/osquery.conf

# Set permissions
sudo chown osquery:osquery /etc/osquery/osquery.conf
sudo chmod 644 /etc/osquery/osquery.conf
```

### 3. Download OSQuery Packs

```bash
# Download official packs from OSQuery GitHub
cd /etc/osquery/packs

# Incident Response Pack
sudo curl -L -o incident-response.conf https://raw.githubusercontent.com/osquery/osquery/master/packs/incident-response.conf

# OSSEC Rootkit Detection Pack
sudo curl -L -o ossec-rootkit.conf https://raw.githubusercontent.com/osquery/osquery/master/packs/ossec-rootkit.conf

# IT Compliance Pack
sudo curl -L -o it-compliance.conf https://raw.githubusercontent.com/osquery/osquery/master/packs/it-compliance.conf

# Set permissions
sudo chown osquery:osquery *
sudo chmod 644 *
```

### 4. Test Configuration

```bash
# Test configuration syntax
sudo osqueryd --config_path /etc/osquery/osquery.conf --config_check

# Run one-time queries to verify
osqueryi

# Inside osqueryi shell:
SELECT * FROM system_info;
SELECT * FROM processes LIMIT 5;
SELECT * FROM listening_ports;
.exit
```

##  Running OSQuery Daemon

### Start the Service

```bash
# Enable and start osqueryd
sudo systemctl enable osqueryd
sudo systemctl start osqueryd

# Verify it's running
sudo systemctl status osqueryd

# View logs
sudo tail -f /var/log/osquery/osqueryd.results.log
```

### Stop/Restart

```bash
# Stop service
sudo systemctl stop osqueryd

# Restart service
sudo systemctl restart osqueryd
```

##  Understanding the Output

### Log File Location
```
/var/log/osquery/osqueryd.results.log
```

### Log Format Example
```json
{
  "name": "system_info",
  "hostIdentifier": "john-System",
  "calendarTime": "Fri Jan 12 10:30:45 2024 UTC",
  "unixTime": 1705062645,
  "epoch": 0,
  "counter": 0,
  "numerics": false,
  "action": "added",
  "columns": {
    "host_uuid": "12345678-1234-1234-1234-123456789012",
    "hostname": "john-System",
    "uuid": "12345678-1234-1234-1234-123456789012",
    "user_uuid": "12345678-1234-1234-1234-123456789012",
    "cpu_brand": "Intel(R) Core(TM) i5-9400 CPU @ 2.90GHz",
    "cpu_physical_cores": "6",
    "cpu_logical_cores": "6",
    "cpu_micro_code": "0x8c",
    "hardware_vendor": "System manufacturer",
    "hardware_model": "System Product Name",
    "hardware_version": "System Version",
    "board_vendor": "ASUSTeK COMPUTER INC.",
    "board_model": "H110M-K",
    "board_version": "Rev 1.xx",
    "board_serial": "180621001234567",
    "chassis_vendor": "System manufacturer",
    "chassis_model": "System Product Name",
    "chassis_version": "System Version",
    "chassis_serial": "System Serial Number"
  }
}
```

##  Integration with Loki

The OSQuery logs are automatically collected by Alloy and sent to Loki:

### Query in Grafana
```logql
# All OSQuery logs
{job="osquery"}

# Rootkit detection results
{job="osquery"} | json | name="file_suspicious_artifacts"

# Process anomalies
{job="osquery"} | json | name="hidden_processes"

# Network threats
{job="osquery"} | json | name=~"listening_ports|process_open_sockets"

# Persistence mechanisms
{job="osquery"} | json | name=~"crontab|systemd_units|authorized_keys"

# Privilege escalation attempts
{job="osquery"} | json | name=~"suid_bin|kernel_modules"
```

##  Integration with Falco

Both Falco and OSQuery provide complementary detection:

| Component | Detection Type | Advantage |
|-----------|----------------|-----------|
| **Falco** | Runtime behavioral | Real-time threat detection |
| **OSQuery** | Compliance/inventory | System state baseline |

### Combined Queries in Grafana

```logql
# Falco alert + OSQuery confirmation
{job="falco"} | json | rule="Suspicious Process"
AND
{job="osquery"} | json | name="processes"
```

##  Customization

### Add New Queries

Edit `/etc/osquery/osquery.conf` and add to the `schedule` section:

```json
"custom_query": {
  "query": "SELECT * FROM custom_table;",
  "interval": 900,
  "description": "Custom monitoring",
  "value": "Monitoring purpose"
}
```

Then restart:
```bash
sudo systemctl restart osqueryd
```

### Adjust Intervals

- **High priority** (exploits, persistence): 300-600 seconds
- **Medium priority** (changes, anomalies): 900-1800 seconds
- **Low priority** (baselines, compliance): 3600+ seconds

##  Performance Tuning

### Memory Limits

Edit `/etc/osquery/osquery.conf`:
```json
"disable_memory_limit": false,
"memory_limit_percent": 10
```

### Worker Threads

```json
"worker_threads": 4
```

Increase if you have more CPU cores, decrease to reduce memory usage.

##  Troubleshooting

### OSQuery Not Starting

```bash
# Check service status
sudo systemctl status osqueryd

# Check logs
sudo journalctl -u osqueryd -n 50

# Test configuration
sudo osqueryd --config_path /etc/osquery/osquery.conf --config_check
```

### No Logs Being Generated

```bash
# Check osquery process
ps aux | grep osqueryd

# Check permissions on log directory
ls -la /var/log/osquery/

# Manually test query
osqueryi "SELECT * FROM processes LIMIT 1;"
```

### High CPU/Memory Usage

```bash
# Reduce query frequency
# Increase intervals in osquery.conf

# Disable heavy queries
# Comment out memory_map, process_envs, etc.

# Restart service
sudo systemctl restart osqueryd
```

### Logs Not Appearing in Loki

1. Verify OSQuery is running:
   ```bash
   sudo systemctl status osqueryd
   ```

2. Verify logs are being generated:
   ```bash
   sudo tail -f /var/log/osquery/osqueryd.results.log
   ```

3. Verify Alloy is running:
   ```bash
   docker-compose ps alloy
   ```

4. Check Alloy config includes OSQuery:
   ```bash
   cat /home/john/loki/alloy-local-config.yaml | grep osquery
   ```

##  Common Exploit Detection

### Rootkit Detection
- **Query**: `file_suspicious_artifacts`
- **Interval**: 600 seconds
- **Detects**: Known rootkits (Knark, SUCKIT, Adore, Reptile, Beurk)

### Privilege Escalation
- **Query**: `suid_bin`, `kernel_modules`, `sudo_users`
- **Interval**: 1800 seconds
- **Detects**: New SUID binaries, kernel module loading, sudoers changes

### Persistence Mechanisms
- **Query**: `crontab`, `systemd_units`, `authorized_keys`, `shell_history`
- **Interval**: 300-900 seconds
- **Detects**: New scheduled tasks, SSH backdoors, malicious commands

### Network Exploitation
- **Query**: `listening_ports`, `process_open_sockets`, `iptables`
- **Interval**: 600-900 seconds
- **Detects**: Rogue backdoors, C2 communications, firewall changes

### Memory Exploitation
- **Query**: `process_memory_map`, `process_envs`, `hidden_processes`
- **Interval**: 1800 seconds
- **Detects**: Code injection, preload attacks, hidden processes

##  References

- [OSQuery Documentation](https://osquery.io/docs)
- [OSQuery Tables](https://osquery.io/schema)
- [OSQuery Packs](https://github.com/osquery/osquery/tree/master/packs)
- [Detecting Linux Exploits with OSQuery](https://osquery.io/docs/guides/linux-security)

##  Verification Checklist

After installation, verify:

```bash
 osquery is installed: osqueryi --version
 Configuration is valid: sudo osqueryd --config_check
 Service is running: sudo systemctl status osqueryd
 Logs are being generated: ls -lah /var/log/osquery/
 Alloy is collecting: docker-compose logs alloy | grep osquery
 Logs in Grafana: Query {job="osquery"} in Loki
 Rootkit detection working: Check suspicious_artifacts queries
 Persistence detection working: Check crontab/systemd queries
```

---

**Status**: Ready for Deployment
**Tested**: Linux (Ubuntu 20.04+, Debian 11+)


## OSQUERY_PROFILES.md

# osquery Profiles

This repository now supports multiple `osqueryd` operating profiles so you can choose between lower-noise continuous monitoring and higher-volume forensic collection.

## Profile summary

| Profile | Intended use | Query style | Packs | Relative volume |
|---|---|---|---|---|
| `quiet` | Default always-on workstation or lab monitoring | bounded inventories, suspicious subsets, slower heavy schedules | `rootkit_detection` | medium |
| `deep-forensic` | Temporary incident response, threat hunting, or deep triage | fuller process, environment, memory map, package, and Docker visibility | `incident_response`, `rootkit_detection`, `compliance` | high |
| `ssd-optimized` | Lowest-write hosts or constrained systems | smallest schedule breadth and longest intervals | none | lowest |

## Quiet profile

File: `osqueryd.conf`

Use the quiet profile when you want `osqueryd` running continuously with a lower-noise event stream.

Key characteristics:

- keeps the repo-local log path used by Alloy and the OTel collector
- preserves rootkit-oriented detection in both scheduled queries and the `ossec-rootkit` pack
- narrows high-volume tables like `process_envs` and `process_memory_map`
- reduces package and Docker inventory churn
- disables the noisier incident-response and compliance packs by default

This is the default profile installed when you run:

- `sudo ./setup-osqueryd.sh configure`
- `sudo ./setup-osqueryd.sh configure quiet`

## Deep forensic profile

File: `osqueryd-deep-forensic.conf`

Use the deep forensic profile when you are actively investigating a host and want broader state visibility even if it produces significantly more logs.

Key characteristics:

- restores full `processes`, `process_envs`, `process_memory_map`, and `process_open_pipes` coverage
- restores fuller package and Docker inventories
- enables the official `incident_response`, `rootkit_detection`, and `compliance` packs
- keeps the same repo-local log path so Loki and OpenObserve continue to work without reconfiguration

Switch to it with:

- `sudo ./setup-osqueryd.sh configure deep-forensic`
- `sudo systemctl restart osqueryd`

## SSD-optimized profile

File: `osqueryd-ssd-optimized.conf`

Use this profile when write minimization matters more than coverage depth.

Switch to it with:

- `sudo ./setup-osqueryd.sh configure ssd-optimized`
- `sudo systemctl restart osqueryd`

## Switching profiles

The helper script installs the selected profile to `/etc/osquery/osquery.conf` and records the active choice in `/etc/osquery/osquery.profile`.

Common commands:

- `sudo ./setup-osqueryd.sh profiles`
- `sudo ./setup-osqueryd.sh configure quiet`
- `sudo ./setup-osqueryd.sh configure deep-forensic`
- `sudo ./setup-osqueryd.sh configure ssd-optimized`
- `sudo ./setup-osqueryd.sh status`

## Recommended usage

- start with `quiet` for normal daily monitoring
- switch to `deep-forensic` only when you need broader forensic visibility
- switch back to `quiet` after the investigation to reduce ongoing log volume
- use `ssd-optimized` only when host write minimization is the overriding goal

## Rootkit detection note

Rootkit-focused coverage is preserved in both the `quiet` and `deep-forensic` profiles.

That means both profiles keep:

- rootkit-oriented scheduled queries such as `file_suspicious_artifacts`, `hidden_processes`, and `suspicious_library_paths`
- the `rootkit_detection` pack mapping to `/etc/osquery/packs/ossec-rootkit.conf`


## OSQUERY-TABLES.md



## OSQUERY_CONFIGURATION_SUMMARY.md

# OSQuery Configuration Summary

##  What Was Created

A comprehensive `osqueryd.conf` file optimized for detecting Linux exploits, rootkits, and security threats on your system.

##  Detection Coverage

### Persistence Mechanisms (5 queries)
- Crontab jobs (scheduled persistence)
- Systemd units (service-based backdoors)
- SSH authorized_keys (key-based persistence)
- Shell history (attacker commands)
- Startup items (boot persistence)

### Privilege Escalation (4 queries)
- SUID binaries (privesc vectors)
- Sudoers configuration (unauthorized access)
- Kernel modules (kernel rootkits)
- Kernel keys (kernel manipulation)

### Rootkit/Malware Detection (3 queries)
- Suspicious file artifacts (known rootkits)
- Hidden processes (process hiding)
- Suspicious library paths (injection attacks)

### Network Exploitation (6 queries)
- Listening ports (backdoors)
- Open sockets (C2 communications)
- ARP cache (MITM attacks)
- Iptables rules (firewall changes)
- Routes (route hijacking)
- DNS resolvers (DNS poisoning)

### File System Attacks (4 queries)
- Critical file changes (integrity monitoring)
- Suspicious file artifacts (rootkits)
- Process open files (unauthorized access)
- SUID binary changes (new backdoors)

### Process & Memory Exploitation (4 queries)
- Process snapshots (baseline)
- Process environment variables (LD_PRELOAD attacks)
- Process memory maps (code injection)
- Process named pipes (command injection)

### User & Authentication (7 queries)
- System users (backdoor accounts)
- System groups (privilege groups)
- Logged-in users (unauthorized access)
- Last logins (access history)
- SSH keys (key-based backdoors)
- Authorized keys (SSH persistence)
- Sudoers config (unauthorized privileges)

### Kernel & Hardware Security (4 queries)
- Secure Boot status (firmware security)
- SELinux settings (mandatory access control)
- AppArmor profiles (app sandboxing)
- Secure Boot certificates (firmware integrity)

### Package Management (2 queries)
- Debian packages (installed malware)
- RPM packages (installed malware)

### Container Security (3 queries)
- Docker containers (container breakouts)
- Docker images (malicious images)
- Docker info (daemon security)

**Total: 42 monitoring queries**

##  Configuration Structure

```json
{
  "options": {
    "config_plugin": "filesystem",
    "logger_plugin": "filesystem",
    "logger_path": "/var/log/osquery",
    "worker_threads": 4,
    "memory_limit_percent": 10
  },
  "schedule": {
    // 42 queries organized by category
    "system_info": { ... },
    "crontab": { ... },
    "suid_bin": { ... },
    // ... etc
  },
  "decorators": {
    // Auto-add system info to all logs
    "load": [
      "SELECT uuid AS host_uuid FROM system;",
      "SELECT user AS username FROM logged_in_users ORDER BY time DESC LIMIT 1;",
      "SELECT hostname FROM system_info;",
      "SELECT version FROM os_version;"
    ]
  },
  "packs": {
    // Reference official OSQuery packs
    "incident_response": "/etc/osquery/packs/incident-response.conf",
    "rootkit_detection": "/etc/osquery/packs/ossec-rootkit.conf",
    "compliance": "/etc/osquery/packs/it-compliance.conf"
  }
}
```

##  Query Intervals

| Category | Interval | Rationale |
|----------|----------|-----------|
| High-priority (exploits) | 300-600s | Fast detection needed |
| Medium-priority (changes) | 900-1800s | Moderate importance |
| Low-priority (baselines) | 3600s | Historical baseline |

##  Example Detections

### Rootkit Detection
```json
"file_suspicious_artifacts": {
  "query": "SELECT * FROM file WHERE path IN ('/tmp/.X11-unix/.pizda', ...);",
  "interval": 600,
  "value": "Detect known rootkits: Knark, SUCKIT, Adore, Reptile, Beurk"
}
```

**Known Rootkits Detected:**
- Knark
- SUCKIT
- Adore
- Reptile
- Beurk
- LRK
- T0rn
- Showtee
- And 40+ more...

### Privilege Escalation
```json
"suid_bin": {
  "query": "SELECT * FROM suid_bin;",
  "interval": 1800,
  "value": "Detect dropped/modified SUID binaries"
}
```

### Persistence Mechanisms
```json
"crontab": {
  "query": "SELECT * FROM crontab;",
  "interval": 900,
  "value": "Identify malware using cron for persistence"
}
```

##  Query Categories

### 1. System Information
- Basic system stats
- OS version
- Kernel info
- Uptime

### 2. Persistence Mechanisms
- Cron jobs
- Systemd units
- SSH keys
- Shell history
- Startup items

### 3. Privilege Escalation
- SUID binaries
- Sudoers config
- Kernel modules
- Kernel keys

### 4. Rootkit/Malware Detection
- Suspicious artifacts
- Hidden processes
- Suspicious library paths

### 5. Network Exploitation
- Listening ports
- Open sockets
- ARP cache
- Firewall rules
- Routes
- DNS resolvers

### 6. File System Attacks
- Critical file changes
- Process file access
- SUID changes

### 7. Process & Memory
- Running processes
- Environment variables
- Memory maps
- Named pipes

### 8. User & Authentication
- Users
- Groups
- Logged-in users
- Logins history
- SSH keys
- Sudoers

### 9. Kernel & Hardware
- Secure Boot
- SELinux
- AppArmor
- Certificates

### 10. Package Management
- Debian packages
- RPM packages

### 11. Container Security
- Docker containers
- Docker images
- Docker daemon

##  Integration Points

### With Loki
- Logs to: `/var/log/osquery/osqueryd.results.log`
- Format: JSON
- Label: `job=osquery`
- Collected by: Alloy

### With Falco
- Complementary detection
- Falco: Real-time behavioral
- OSQuery: System state baseline

### Combined Queries
```logql
# Falco detected suspicious process
{job="falco"} | json | rule="Suspicious Process"

# OSQuery confirms with process info
{job="osquery"} | json | name="processes"
```

##  Customization Options

### Add Custom Query
Edit `osqueryd.conf` `schedule` section:
```json
"my_query": {
  "query": "SELECT * FROM table;",
  "interval": 600,
  "description": "My custom query"
}
```

### Disable Queries
Comment out or remove from schedule

### Change Intervals
Modify `interval` value (in seconds)

### Add External Packs
Reference in `packs` section

##  Performance Impact

### CPU: ~1-3% (varies by query intensity)
### Memory: ~50-200MB (depends on query results)
### Disk I/O: Minimal
### Network: None (local logging only)

### Tuning Options
```json
"worker_threads": 4,           // CPU threads
"memory_limit_percent": 10,    // Max memory %
"disable_memory_limit": false
```

##  Verification

After setup:
```bash
# Config is valid
sudo osqueryd --config_check

# Service running
sudo systemctl status osqueryd

# Logs generating
tail -f /var/log/osquery/osqueryd.results.log

# In Loki
Query: {job="osquery"}
```

##  Exploit Types Detected

### Rootkits
- Kernel-level rootkits
- File-based rootkits
- Library injection rootkits
- Process hiding rootkits

### Privilege Escalation
- SUID binary exploitation
- Kernel module exploitation
- Sudo misconfigurations

### Persistence
- Cron backdoors
- Systemd backdoors
- SSH key persistence
- Startup persistence

### Lateral Movement
- Unauthorized users
- SSH key backdoors
- Firewall rules changes
- Network redirects

### Data Exfiltration
- Unauthorized listening ports
- Suspicious connections
- Network changes

### Malware
- Malware artifacts
- Malware persistence
- Malware libraries

##  Security Considerations

### What OSQuery DOES
 Detect system state changes
 Identify known malware artifacts
 Monitor file integrity
 Track user access
 Monitor network configuration

### What OSQuery DOES NOT
 Real-time syscall monitoring (use Falco)
 Behavioral anomaly detection
 Network packet analysis
 Memory introspection

**Recommendation**: Use OSQuery + Falco together for comprehensive detection

##  Files in This Configuration

```
/home/john/loki/
 osqueryd.conf                      Main config (this file)
 OSQUERY_SETUP_GUIDE.md             Installation guide
 OSQUERY_QUICK_REFERENCE.md         Quick reference
 OSQUERY_CONFIGURATION_SUMMARY.md   This summary
```

##  Support

- **Installation**: See `OSQUERY_SETUP_GUIDE.md`
- **Quick Setup**: See `OSQUERY_QUICK_REFERENCE.md`
- **Troubleshooting**: See `OSQUERY_SETUP_GUIDE.md` section
- **Configuration Help**: See `osqueryd.conf` comments

---

**Status**: Ready for Deployment
**Version**: 1.0
**Tested**: Linux (Ubuntu 20.04+, Debian 11+)
**Integration**: Loki + Falco + OSQuery


## OSQUERY_QUICK_REFERENCE.md

# OSQuery Quick Reference

##  Quick Setup (5 minutes)

```bash
# 1. Install OSQuery
sudo apt-get install -y osquery

# 2. Create directories
sudo mkdir -p /etc/osquery/packs /var/log/osquery
sudo chown -R osquery:osquery /var/log/osquery

# 3. Copy configuration
sudo cp /home/john/loki/osqueryd.conf /etc/osquery/osquery.conf

# 4. Download packs
cd /etc/osquery/packs
sudo curl -L -o incident-response.conf https://raw.githubusercontent.com/osquery/osquery/master/packs/incident-response.conf
sudo curl -L -o ossec-rootkit.conf https://raw.githubusercontent.com/osquery/osquery/master/packs/ossec-rootkit.conf
sudo curl -L -o it-compliance.conf https://raw.githubusercontent.com/osquery/osquery/master/packs/it-compliance.conf

# 5. Start OSQuery
sudo systemctl enable osqueryd
sudo systemctl start osqueryd

# 6. Verify
sudo systemctl status osqueryd
```

##  Common Queries

### Interactive Shell
```bash
osqueryi
```

### System Information
```sql
SELECT * FROM system_info;
SELECT * FROM os_version;
SELECT * FROM kernel_info;
```

### Process Monitoring
```sql
SELECT * FROM processes WHERE pid > 1000;
SELECT * FROM process_open_sockets WHERE remote_port != 0;
SELECT * FROM process_open_files LIMIT 50;
```

### Rootkit Detection
```sql
SELECT * FROM file WHERE path IN ('/tmp/.X11-unix/.pizda', '/lib/.x', '/dev/tux');
SELECT * FROM kernel_modules;
SELECT * FROM suid_bin;
```

### Persistence Mechanisms
```sql
SELECT * FROM crontab;
SELECT * FROM systemd_units WHERE state = 'running';
SELECT * FROM authorized_keys;
```

### Network Security
```sql
SELECT * FROM listening_ports;
SELECT * FROM arp_cache;
SELECT * FROM iptables;
SELECT * FROM routes;
```

### User & Authentication
```sql
SELECT * FROM users;
SELECT * FROM groups;
SELECT * FROM logged_in_users;
SELECT * FROM sudoers;
```

##  Log Monitoring

### View Real-time Logs
```bash
sudo tail -f /var/log/osquery/osqueryd.results.log
```

### Search for Specific Queries
```bash
grep "suid_bin" /var/log/osquery/osqueryd.results.log
grep "file_suspicious_artifacts" /var/log/osquery/osqueryd.results.log
```

##  Loki Integration

### Query in Grafana
```logql
# All OSQuery logs
{job="osquery"}

# Rootkit artifacts
{job="osquery"} | json | name="file_suspicious_artifacts"

# SUID binary changes
{job="osquery"} | json | name="suid_bin"

# Cron jobs
{job="osquery"} | json | name="crontab"

# Network ports
{job="osquery"} | json | name="listening_ports"

# Kernel modules (rootkit detection)
{job="osquery"} | json | name="kernel_modules"
```

##  Service Management

```bash
# Start/stop/restart
sudo systemctl start osqueryd
sudo systemctl stop osqueryd
sudo systemctl restart osqueryd

# Check status
sudo systemctl status osqueryd
sudo journalctl -u osqueryd -n 50

# View configuration
sudo osqueryd --config_path /etc/osquery/osquery.conf --config_check

# Test configuration without starting
sudo osqueryd -S --config_path /etc/osquery/osquery.conf
```

##  Configuration Tweaks

### Add Custom Query
Edit `/etc/osquery/osquery.conf`:
```json
"my_custom_query": {
  "query": "SELECT * FROM processes LIMIT 100;",
  "interval": 600,
  "description": "Custom process monitoring"
}
```

### Disable Heavy Queries
Comment out in config:
```json
// "process_memory_map": { ... },
// "process_envs": { ... }
```

### Change Log Interval
```json
"system_info": {
  "query": "SELECT * FROM system_info;",
  "interval": 1800  // Changed from 3600
}
```

##  Troubleshooting

| Problem | Solution |
|---------|----------|
| OSQuery not starting | Check: `sudo osqueryd --config_check` |
| No logs generated | Verify permission on `/var/log/osquery/` |
| High CPU usage | Increase intervals, disable heavy queries |
| Loki not receiving | Check Alloy config includes osquery path |

##  Detection Capabilities

###  Detects
- Rootkits (Knark, SUCKIT, Adore, Reptile, Beurk, etc.)
- Privilege escalation attempts
- Persistence mechanisms (cron, systemd, SSH)
- Unauthorized user accounts
- SSH backdoors
- Kernel module loading
- Suspicious network connections
- Memory injection attacks
- Library preload attacks
- Container escape attempts

###  Does NOT Detect (Use Falco)
- Real-time syscall monitoring
- Behavioral anomalies
- Suspicious capability usage
- Abnormal file access patterns
- Network protocol violations

##  Best Practices

1. **Don't run too many heavy queries** - Memory impact
2. **Use appropriate intervals** - Fast for critical, slow for baselines
3. **Monitor the logs** - Check `/var/log/osquery/` regularly
4. **Test new configs** - Always run `--config_check` first
5. **Correlate with Falco** - Use both for complete picture
6. **Review packs regularly** - Update from official sources

##  References

- OSQuery Docs: https://osquery.io/docs
- Schema: https://osquery.io/schema
- GitHub Packs: https://github.com/osquery/osquery/tree/master/packs

---

**Remember**: OSQuery is your system inventory and compliance tool. Use Falco for real-time threat detection!


## OSQUERYD_QUICK_START.md

# osqueryd Quick Start Guide

This guide will help you set up osqueryd on your host machine to work with the Grafana Loki + Alloy log collection stack.

## Prerequisites

1. **osqueryd installed**: The osquery package must be installed on your system
   ```bash
   # Ubuntu/Debian
   sudo apt-get update && sudo apt-get install -y osquery
   
   # CentOS/RHEL
   sudo yum install -y osquery
   
   # macOS
   brew install osquery
   ```

2. **Verify installation**:
   ```bash
   osqueryd --version
   osqueryi
   ```

## Quick Setup (One Command)

The fastest way to set up osqueryd is to use the automated script:

```bash
sudo /home/john/loki/setup-osqueryd.sh setup
```

This will:
-  Verify osquery is installed
-  Create necessary directories (`/etc/osquery`, repo-local `./.data/osquery`)
-  Copy the configuration file and flagfile
-  Download official osquery packs (incident-response, rootkit, compliance)
-  Validate the configuration
-  Enable the osqueryd service
-  Start the service
-  Check initial logs

## Step-by-Step Manual Setup

If you prefer to set up manually or troubleshoot, follow these steps:

### 1. Create Required Directories

```bash
sudo mkdir -p /etc/osquery/packs /var/log/osquery
sudo chown -R osquery:osquery /etc/osquery /var/log/osquery
sudo chmod 755 /etc/osquery /var/log/osquery /etc/osquery/packs
```

### 2. Copy Configuration

```bash
sudo cp /home/john/loki/osqueryd.conf /etc/osquery/osquery.conf
sudo chown osquery:osquery /etc/osquery/osquery.conf
sudo chmod 644 /etc/osquery/osquery.conf
```

### 3. Download Packs

```bash
cd /etc/osquery/packs

# Download incident response pack
sudo curl -L -o incident-response.conf \
  https://raw.githubusercontent.com/osquery/osquery/master/packs/incident-response.conf

# Download rootkit detection pack
sudo curl -L -o ossec-rootkit.conf \
  https://raw.githubusercontent.com/osquery/osquery/master/packs/ossec-rootkit.conf

# Download compliance pack
sudo curl -L -o it-compliance.conf \
  https://raw.githubusercontent.com/osquery/osquery/master/packs/it-compliance.conf

# Fix permissions
sudo chown osquery:osquery *.conf
sudo chmod 644 *.conf
```

### 4. Validate Configuration

```bash
# Quick JSON validation
python3 -m json.tool /etc/osquery/osquery.conf > /dev/null && echo " Config is valid JSON"

# Full validation
sudo osqueryd --config_path /etc/osquery/osquery.conf --config_check
```

### 5. Enable and Start Service

```bash
# Enable on boot
sudo systemctl enable osqueryd

# Start the service
sudo systemctl start osqueryd

# Verify it's running
sudo systemctl status osqueryd

# Watch logs in real-time
sudo tail -f /var/log/osquery/osqueryd.results.log
```

## Management Commands

Once setup is complete, use these commands to manage osqueryd:

```bash
# Check service status
sudo systemctl status osqueryd

# View service logs
sudo journalctl -u osqueryd -f

# View osquery results
sudo tail -f /var/log/osquery/osqueryd.results.log

# Restart service
sudo systemctl restart osqueryd

# Stop service
sudo systemctl stop osqueryd

# Interactive query tool using the repo helper
/home/john/loki/osqueryi-local.sh
```

## Using the Setup Script Commands

The `setup-osqueryd.sh` script provides many useful commands:

```bash
# Show help
sudo /home/john/loki/setup-osqueryd.sh help

# Complete setup (recommended first run)
sudo /home/john/loki/setup-osqueryd.sh setup

# Just configure (copy config, copy flagfile, and download packs)
sudo /home/john/loki/setup-osqueryd.sh configure

# Download packs
sudo /home/john/loki/setup-osqueryd.sh download

# Validate config
sudo /home/john/loki/setup-osqueryd.sh validate

# Start/stop/restart
sudo /home/john/loki/setup-osqueryd.sh start
sudo /home/john/loki/setup-osqueryd.sh stop
sudo /home/john/loki/setup-osqueryd.sh restart

# View status and recent logs
sudo /home/john/loki/setup-osqueryd.sh status

# Run test query
sudo /home/john/loki/setup-osqueryd.sh test

# Follow logs
sudo /home/john/loki/setup-osqueryd.sh logs

# Clean up logs
sudo /home/john/loki/setup-osqueryd.sh clean
```

## Testing osqueryd

### Test 1: Basic System Info Query

```bash
/home/john/loki/osqueryi-local.sh
> SELECT * FROM system_info;
```

### Test 2: Check Running Processes

```bash
/home/john/loki/osqueryi-local.sh
> SELECT COUNT(*) as process_count FROM processes;
```

### Test 3: List Listening Ports

```bash
/home/john/loki/osqueryi-local.sh
> SELECT * FROM listening_ports LIMIT 5;
```

### Test 4: View osqueryd Results Log

```bash
# After service is running for a minute or two
sudo tail -20 /home/john/loki/.data/osquery/osqueryd.results.log | python3 -m json.tool
```

The results should be JSON-formatted query results that match your configuration schedule.

## Troubleshooting

### Service won't start

```bash
# Check service status and errors
sudo systemctl status osqueryd

# View system journal for osqueryd errors
sudo journalctl -u osqueryd -n 50

# Try running osqueryd manually to see errors
sudo osqueryd --config_path /etc/osquery/osquery.conf --verbose

# Validate config is correct JSON
python3 -m json.tool /etc/osquery/osquery.conf
```

### No logs appearing

```bash
# Check if log directory exists and has correct permissions
ls -la /var/log/osquery/

# Service must be running for logs to appear
sudo systemctl status osqueryd

# Give it a moment - initial queries may take a few seconds
sleep 5 && sudo tail -f /var/log/osquery/osqueryd.results.log
```

### Permission denied errors

```bash
# Verify osquery user exists
id osquery

# Fix permissions
sudo chown -R osquery:osquery /etc/osquery /var/log/osquery
sudo chmod -R 755 /etc/osquery /var/log/osquery
```

### Config validation fails

```bash
# Check config is valid JSON
python3 -m json.tool /etc/osquery/osquery.conf

# Run osqueryd config check with verbosity
sudo osqueryd --config_path /etc/osquery/osquery.conf --config_check --verbose

# Make sure all referenced pack files exist
ls -la /etc/osquery/packs/
```

## Integration with Loki + Alloy

Once osqueryd is running and logging to `/var/log/osquery/osqueryd.results.log`:

1. **Verify Alloy is configured** to read osquery logs:
   ```bash
   grep -A 10 "osquery" /home/john/loki/alloy-local-config.yaml
   ```

2. **Start the Loki stack**:
   ```bash
   cd /home/john/loki
   ./start-loki.sh start
   ```

3. **Query osquery logs in Grafana**:
   - Go to http://localhost:3000 (admin/admin)
   - Select Loki datasource in Explore
   - Run query: `{job="osquery"}`
   - Or filter by specific content: `{job="osquery"} | json`

## What's Being Monitored

The osqueryd configuration includes scheduled queries for:

- **System Information**: OS version, kernel, hardware details
- **Persistence Mechanisms**: Cron jobs, systemd services, shell history
- **Privilege Escalation**: SUID binaries, sudoers configuration
- **Rootkits & Malware**: Suspicious artifacts, hidden processes, library paths
- **Network Security**: Listening ports, connections, firewall rules, DNS
- **File System**: Critical file changes, mounts, permissions
- **Processes & Memory**: Process listings, environment variables, memory maps
- **Users & Authentication**: User accounts, SSH keys, login history
- **Security Controls**: SELinux, AppArmor, Secure Boot
- **Packages & Repositories**: Installed packages, APT/RPM sources
- **Containers**: Docker containers, images, daemon info

See `OSQUERY_SETUP_GUIDE.md` for detailed information about all queries.

## Performance Notes

- Default configuration is moderate-resource: 4 worker threads, 10% memory limit
- Adjust intervals in `osqueryd.conf` if needed (300-600s for critical, 900-1800s for medium, 3600s for baseline)
- Monitor CPU/memory with: `sudo top -p $(pidof osqueryd)`
- Disable heavy queries like `process_memory_map` if host is resource-constrained


## OSquery-linux-queries.md

[**Get installed Chrome Extensions**](https://fleetdm.com/reports/get-installed-chrome-extensions)

List installed Chrome Extensions for all users.

[Read more](https://fleetdm.com/reports/get-installed-chrome-extensions)  
[**Get installed Windows software**](https://fleetdm.com/reports/get-installed-windows-software)

Get all software installed on a Windows computer, including programs, browser plugins, and installed packages. Note that this does not include other running processes in the processes table.

[Read more](https://fleetdm.com/reports/get-installed-windows-software)  
[**Get current users with active shell/console on the system**](https://fleetdm.com/reports/get-current-users-with-active-shell-console-on-the-system)

Get current users with active shell/console on the system and associated process

[Read more](https://fleetdm.com/reports/get-current-users-with-active-shell-console-on-the-system)  
[**Get unencrypted SSH keys for local accounts**](https://fleetdm.com/reports/get-unencrypted-ssh-keys-for-local-accounts)

Identify SSH keys created without a passphrase which can be used in Lateral Movement (MITRE. TA0008)

[Read more](https://fleetdm.com/reports/get-unencrypted-ssh-keys-for-local-accounts)  
[**Get unencrypted SSH keys for domain-joined accounts**](https://fleetdm.com/reports/get-unencrypted-ssh-keys-for-domain-joined-accounts)

Identify SSH keys created without a passphrase which can be used in Lateral Movement (MITRE. TA0008)

[Read more](https://fleetdm.com/reports/get-unencrypted-ssh-keys-for-domain-joined-accounts)  
[**Get network interfaces**](https://fleetdm.com/reports/get-network-interfaces)

Network interfaces MAC address

[Read more](https://fleetdm.com/reports/get-network-interfaces)  
[**Get local user accounts**](https://fleetdm.com/reports/get-local-user-accounts)

Local user accounts (including domain accounts that have logged on locally (Windows)).

[Read more](https://fleetdm.com/reports/get-local-user-accounts)  
[**Get Nmap scanner**](https://fleetdm.com/reports/get-nmap-scanner)

Get Nmap scanner process, as well as its user, parent, and process details.

[Read more](https://fleetdm.com/reports/get-nmap-scanner)  
[**Get Windows print spooler remote code execution vulnerability**](https://fleetdm.com/reports/get-windows-print-spooler-remote-code-execution-vulnerability)

Detects devices that are potentially vulnerable to CVE-2021-1675 because the print spooler service is not disabled.

[Read more](https://fleetdm.com/reports/get-windows-print-spooler-remote-code-execution-vulnerability)  
[**Get local users and their privileges**](https://fleetdm.com/reports/get-local-users-and-their-privileges)

Collects the local user accounts and their respective user group.

[Read more](https://fleetdm.com/reports/get-local-users-and-their-privileges)  
[**Get processes that no longer exist on disk**](https://fleetdm.com/reports/get-processes-that-no-longer-exist-on-disk)

Lists all processes of which the binary which launched them no longer exists on disk. Attackers often delete files from disk after launching a process to mask presence.

[Read more](https://fleetdm.com/reports/get-processes-that-no-longer-exist-on-disk)  
[**Get all listening ports, by process**](https://fleetdm.com/reports/get-all-listening-ports-by-process)

List ports that are listening on all interfaces, along with the process to which they are attached.

[Read more](https://fleetdm.com/reports/get-all-listening-ports-by-process)  
[**Get whether TeamViewer is installed/running**](https://fleetdm.com/reports/get-whether-team-viewer-is-installed-running)

Looks for the TeamViewer service running on machines. This is often used when attackers gain access to a machine, running TeamViewer to allow them to access a machine.

[Read more](https://fleetdm.com/reports/get-whether-team-viewer-is-installed-running)  
[**Get malicious Python backdoors**](https://fleetdm.com/reports/get-malicious-python-backdoors)

Watches for the backdoored Python packages installed on the system. See (http://www.nbu.gov.sk/skcsirt-sa-20170909-pypi/index.html)

[Read more](https://fleetdm.com/reports/get-malicious-python-backdoors)  
[**Check for artifacts of the Floxif trojan**](https://fleetdm.com/reports/check-for-artifacts-of-the-floxif-trojan)

Checks for artifacts from the Floxif trojan on Windows machines.

[Read more](https://fleetdm.com/reports/check-for-artifacts-of-the-floxif-trojan)  
[**Get Shimcache table**](https://fleetdm.com/reports/get-shimcache-table)

Returns forensic data showing evidence of likely file execution, in addition to the last modified timestamp of the file, order of execution, full file path order of execution, and the order in which files were executed.

[Read more](https://fleetdm.com/reports/get-shimcache-table)  
[**Get applications hogging memory**](https://fleetdm.com/reports/get-applications-hogging-memory)

Returns top 10 applications or processes hogging memory the most.

[Read more](https://fleetdm.com/reports/get-applications-hogging-memory)  
[**Get servers with root login in the last 24 hours**](https://fleetdm.com/reports/get-servers-with-root-login-in-the-last-24-hours)

Returns servers with root login in the last 24 hours and the time the users were logged in.

[Read more](https://fleetdm.com/reports/get-servers-with-root-login-in-the-last-24-hours)  
[**Get operating system information**](https://fleetdm.com/reports/get-operating-system-information)

Returns the operating system name and version on the device.

[Read more](https://fleetdm.com/reports/get-operating-system-information)  
[**Get antivirus status from the Windows Security Center**](https://fleetdm.com/reports/get-antivirus-status-from-the-windows-security-center)

Selects the antivirus and signatures status from Windows Security Center.

[Read more](https://fleetdm.com/reports/get-antivirus-status-from-the-windows-security-center)  
[**Discover TLS certificates**](https://fleetdm.com/reports/discover-tls-certificates)

Retrieves metadata about TLS certificates for servers listening on the local machine. Enables mTLS adoption analysis and cert expiration notifications.

[Read more](https://fleetdm.com/reports/discover-tls-certificates)  
[**Geolocate via ipapi.co**](https://fleetdm.com/reports/geolocate-via-ipapi-co)

Geolocate a host using the \[ipapi.co\](https://ipapi.co) in an emergency. Requires the curl table. \[Learn more\](https://fleetdm.com/guides/locate-assets-with-osquery).

[Read more](https://fleetdm.com/reports/geolocate-via-ipapi-co)  
[**Get a list of Visual Studio Code extensions**](https://fleetdm.com/reports/get-a-list-of-visual-studio-code-extensions)

Get a list of installed VS Code extensions (requires osquery \> 5.11.0).

[Read more](https://fleetdm.com/reports/get-a-list-of-visual-studio-code-extensions)  
[**List osquery table names**](https://fleetdm.com/reports/list-osquery-table-names)

List all table names in the schema of the currently installed version of osquery

[Read more](https://fleetdm.com/reports/list-osquery-table-names)  
[**Get MCP client configurations**](https://fleetdm.com/reports/get-mcp-client-configurations)

Retrieves Model Context Protocol (MCP) client configurations from supported AI applications. Only global (not project-specific) configurations are returned. Supported applications: Cursor (macOS/Linux/Windows), Claude Desktop (macOS/Windows), Claude Code (macOS/Linux), VSCode (macOS/Linux/Windows), Windsurf (macOS), Gemini CLI (macOS/Linux/Windows), LMStudio (macOS/Linux/Windows)

[Read more](https://fleetdm.com/reports/get-mcp-client-configurations)  
[**MITRE \- Mount Discovery**](https://fleetdm.com/reports/mitre-mount-discovery)

Check mount on the host \- ATT\&CK T1025,T1052

[Read more](https://fleetdm.com/reports/mitre-mount-discovery)  
[**MITRE \- USB Device Discovery**](https://fleetdm.com/reports/mitre-usb-device-discovery)

Check USB device on the host \- ATT\&CK T1052

[Read more](https://fleetdm.com/reports/mitre-usb-device-discovery)  
[**MITRE \- Chrome Extensions Overview**](https://fleetdm.com/reports/mitre-chrome-extensions-overview)

Lists all chrome extensions \- ATT\&CK T1176

[Read more](https://fleetdm.com/reports/mitre-chrome-extensions-overview)  
[**MITRE \- Firefox Addons**](https://fleetdm.com/reports/mitre-firefox-addons)

Lists all Firefox addons \- ATT\&CK T1176

[Read more](https://fleetdm.com/reports/mitre-firefox-addons)  
[**MITRE \- Opera Extensions**](https://fleetdm.com/reports/mitre-opera-extensions)

Lists all Opera extensions \- ATT\&CK T1176

[Read more](https://fleetdm.com/reports/mitre-opera-extensions)  
[**MITRE \- Process Listening Ports**](https://fleetdm.com/reports/mitre-process-listening-ports)

Returns the Listening port List \- ATT\&CK T1108,T1100,T1029,T1011,T1041,T1048,T1020,T1071,T1219

[Read more](https://fleetdm.com/reports/mitre-process-listening-ports)  
[**MITRE \- Process Network Connections**](https://fleetdm.com/reports/mitre-process-network-connections)

Returns the network connections from system processes \- ATT\&CK T1108,T1100,T1102,T1105,T1039,T1029,T1011,T1041,T1043,T1090,T1094,T1048,T1132,T1020,T1065,T1001,T1071,T1219,T1104,T1008

[Read more](https://fleetdm.com/reports/mitre-process-network-connections)  
[**MITRE \- Process Discovery**](https://fleetdm.com/reports/mitre-process-discovery)

List running processes with non-empty command line. \- ATT\&CK T1059,T1108,T1166,T1100,T1064,T1107,T1003,T1033,T1016,T1082,T1057,T1201,T1083,T1217,T1087,T1072,T1002

[Read more](https://fleetdm.com/reports/mitre-process-discovery)  
[**MITRE \- Active User Sessions**](https://fleetdm.com/reports/mitre-active-user-sessions)

Lists all logged in users \- ATT\&CK T1136,T1078,T1169,T1184,T1021

[Read more](https://fleetdm.com/reports/mitre-active-user-sessions)  
[**MITRE \- User Account Discovery**](https://fleetdm.com/reports/mitre-user-account-discovery)

Lists all create and deleted account \- ATT\&CK T1136,T1078,T1184,T1021

[Read more](https://fleetdm.com/reports/mitre-user-account-discovery)  
[**MITRE \- Chrome Parent Process Validation**](https://fleetdm.com/reports/mitre-chrome-parent-process-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1204

[Read more](https://fleetdm.com/reports/mitre-chrome-parent-process-validation)  
[**MITRE \- CMD Parent Process Validation**](https://fleetdm.com/reports/mitre-cmd-parent-process-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1173,T1204

[Read more](https://fleetdm.com/reports/mitre-cmd-parent-process-validation)  
[**MITRE \- Conhost Parent Process Validation**](https://fleetdm.com/reports/mitre-conhost-parent-process-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1204

[Read more](https://fleetdm.com/reports/mitre-conhost-parent-process-validation)  
[**MITRE \- Firefox Parent Process Validation**](https://fleetdm.com/reports/mitre-firefox-parent-process-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1204

[Read more](https://fleetdm.com/reports/mitre-firefox-parent-process-validation)  
[**MITRE \- Internet Explorer Parent Process Validation**](https://fleetdm.com/reports/mitre-internet-explorer-parent-process-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1204

[Read more](https://fleetdm.com/reports/mitre-internet-explorer-parent-process-validation)  
[**MITRE \- LSASS Parent Process Validation**](https://fleetdm.com/reports/mitre-lsass-parent-process-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1204

[Read more](https://fleetdm.com/reports/mitre-lsass-parent-process-validation)  
[**MITRE \- Notepad Plus Plus Parent Process Validation**](https://fleetdm.com/reports/mitre-notepad-plus-plus-parent-process-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1204

[Read more](https://fleetdm.com/reports/mitre-notepad-plus-plus-parent-process-validation)  
[**MITRE \- Notepad Parent Process Validation**](https://fleetdm.com/reports/mitre-notepad-parent-process-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1204

[Read more](https://fleetdm.com/reports/mitre-notepad-parent-process-validation)  
[**MITRE \- PowerShell Parent Process Validation**](https://fleetdm.com/reports/mitre-power-shell-parent-process-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1173,T1086,T1204

[Read more](https://fleetdm.com/reports/mitre-power-shell-parent-process-validation)  
[**MITRE \- Services Parent Process Validation**](https://fleetdm.com/reports/mitre-services-parent-process-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1204

[Read more](https://fleetdm.com/reports/mitre-services-parent-process-validation)  
[**MITRE \- Svchost Parent Process Validation**](https://fleetdm.com/reports/mitre-svchost-parent-process-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1204

[Read more](https://fleetdm.com/reports/mitre-svchost-parent-process-validation)  
[**MITRE \- Conhost Path Validation**](https://fleetdm.com/reports/mitre-conhost-path-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1034

[Read more](https://fleetdm.com/reports/mitre-conhost-path-validation)  
[**MITRE \- CSRSS Path Validation**](https://fleetdm.com/reports/mitre-csrss-path-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1034

[Read more](https://fleetdm.com/reports/mitre-csrss-path-validation)  
[**MITRE \- DLLHost Path Validation**](https://fleetdm.com/reports/mitre-dll-host-path-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1034

[Read more](https://fleetdm.com/reports/mitre-dll-host-path-validation)  
[**MITRE \- Explorer Path Validation**](https://fleetdm.com/reports/mitre-explorer-path-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1034

[Read more](https://fleetdm.com/reports/mitre-explorer-path-validation)  
[**MITRE \- LSASS Path Validation**](https://fleetdm.com/reports/mitre-lsass-path-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1034

[Read more](https://fleetdm.com/reports/mitre-lsass-path-validation)  
[**MITRE \- Services Path Validation**](https://fleetdm.com/reports/mitre-services-path-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1034

[Read more](https://fleetdm.com/reports/mitre-services-path-validation)  
[**MITRE \- SMSS Path Validation**](https://fleetdm.com/reports/mitre-smss-path-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1034

[Read more](https://fleetdm.com/reports/mitre-smss-path-validation)  
[**MITRE \- Svchost Path Validation**](https://fleetdm.com/reports/mitre-svchost-path-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1034

[Read more](https://fleetdm.com/reports/mitre-svchost-path-validation)  
[**MITRE \- Wininit Path Validation**](https://fleetdm.com/reports/mitre-wininit-path-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1034

[Read more](https://fleetdm.com/reports/mitre-wininit-path-validation)  
[**MITRE \- Winlogon Path Validation**](https://fleetdm.com/reports/mitre-winlogon-path-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1034

[Read more](https://fleetdm.com/reports/mitre-winlogon-path-validation)  
[**MITRE \- WMI Provider Path Validation**](https://fleetdm.com/reports/mitre-wmi-provider-path-validation)

Detect processes masquerading as legitimate Windows processes \- ATT\&CK T1034

[Read more](https://fleetdm.com/reports/mitre-wmi-provider-path-validation)  
[**MITRE \- Desktop Registry Monitoring**](https://fleetdm.com/reports/mitre-desktop-registry-monitoring)

Returns the content of the key HKCU\_Control Panel\_Desktop \- ATT\&CK T1180

[Read more](https://fleetdm.com/reports/mitre-desktop-registry-monitoring)  
[**MITRE \- Winlogon Registry Monitoring**](https://fleetdm.com/reports/mitre-winlogon-registry-monitoring)

Returns the content of the key HKCU\_Software\_Microsoft\_WindowsNT\_CurrentVersion\_winlogon \- ATT\&CK T1004

[Read more](https://fleetdm.com/reports/mitre-winlogon-registry-monitoring)  
[**MITRE \- Explorer Run Registry Monitoring**](https://fleetdm.com/reports/mitre-explorer-run-registry-monitoring)

Returns the content of the key HKCU\_Software\_Microsoft\_Windows\_CurrentVersion\_Policies\_Explorer\_Run \- ATT\&CK T1060

[Read more](https://fleetdm.com/reports/mitre-explorer-run-registry-monitoring)  
[**MITRE \- Logon Scripts Registry Monitoring**](https://fleetdm.com/reports/mitre-logon-scripts-registry-monitoring)

Returns the content of the key HKEY\_CURRENT\_USER\_Environment \- ATT\&CK T1037

[Read more](https://fleetdm.com/reports/mitre-logon-scripts-registry-monitoring)  
[**MITRE \- HKCU Run Registry Monitoring**](https://fleetdm.com/reports/mitre-hkcu-run-registry-monitoring)

Returns the content of the key HKCU\_Software\_Microsoft\_Windows\_CurrentVersion\_Run \- ATT\&CK T1060

[Read more](https://fleetdm.com/reports/mitre-hkcu-run-registry-monitoring)  
[**MITRE \- HKLM Winlogon Registry Monitoring**](https://fleetdm.com/reports/mitre-hklm-winlogon-registry-monitoring)

Returns the content of the key HKLM\_Software\_Microsoft\_WindowsNT\_CurrentVersion\_winlogon \- ATT\&CK T1004

[Read more](https://fleetdm.com/reports/mitre-hklm-winlogon-registry-monitoring)  
[**MITRE \- HKLM Explorer Run Registry Monitoring**](https://fleetdm.com/reports/mitre-hklm-explorer-run-registry-monitoring)

Returns the content of the key HKLM\_Software\_Microsoft\_Windows\_CurrentVersion\_Policies\_Explorer\_Run \- ATT\&CK T1060

[Read more](https://fleetdm.com/reports/mitre-hklm-explorer-run-registry-monitoring)  
[**MITRE \- Image File Execution Options Monitoring**](https://fleetdm.com/reports/mitre-image-file-execution-options-monitoring)

Returns the content of the key HKLM\_Image\_File\_Execution\_Options \- ATT\&CK T1015

[Read more](https://fleetdm.com/reports/mitre-image-file-execution-options-monitoring)  
[**MITRE \- AppInit DLLs Registry Monitoring**](https://fleetdm.com/reports/mitre-app-init-dl-ls-registry-monitoring)

Returns the content of the key HKLM\_Software\_Microsoft\_WindowsNT\_CurrentVersion\_Windows for AppInit DLLs \- ATT\&CK T1103

[Read more](https://fleetdm.com/reports/mitre-app-init-dl-ls-registry-monitoring)  
[**MITRE \- WOW64 Winlogon Registry Monitoring**](https://fleetdm.com/reports/mitre-wow-64-winlogon-registry-monitoring)

Returns the content of the key HKLM\_Software\_Wow6432Node\_Microsoft\_WindowsNT\_CurrentVersion\_winlogon \- ATT\&CK T1004

[Read more](https://fleetdm.com/reports/mitre-wow-64-winlogon-registry-monitoring)  
[**MITRE \- WOW64 AppInit DLLs Registry Monitoring**](https://fleetdm.com/reports/mitre-wow-64-app-init-dl-ls-registry-monitoring)

Returns the content of the key HKLM\_Software\_Wow6432Node\_Microsoft\_WindowsNT\_CurrentVersion\_Windows for AppInit DLLs \- ATT\&CK T1103

[Read more](https://fleetdm.com/reports/mitre-wow-64-app-init-dl-ls-registry-monitoring)  
[**MITRE \- Application Shimming Registry Monitoring Custom**](https://fleetdm.com/reports/mitre-application-shimming-registry-monitoring-custom)

Returns the content of the key HKLM\_Software\_Microsoft\_WindowsNT\_CurrentVersion\_appcompatflags\_custom for application shimming \- ATT\&CK T1138

[Read more](https://fleetdm.com/reports/mitre-application-shimming-registry-monitoring-custom)  
[**MITRE \- Application Shimming Registry Monitoring Installed**](https://fleetdm.com/reports/mitre-application-shimming-registry-monitoring-installed)

Returns the content of the key HKLM\_Software\_Microsoft\_WindowsNT\_CurrentVersion\_appcompatflags\_installedsdb for application shimming \- ATT\&CK T1138

[Read more](https://fleetdm.com/reports/mitre-application-shimming-registry-monitoring-installed)  
[**MITRE \- LSA Registry Monitoring**](https://fleetdm.com/reports/mitre-lsa-registry-monitoring)

Returns the content of the key HKLM\_SYSTEM\_CurrentControlSet\_Control\_Lsa \- ATT\&CK T1131

[Read more](https://fleetdm.com/reports/mitre-lsa-registry-monitoring)  
[**MITRE \- Netsh Registry Monitoring**](https://fleetdm.com/reports/mitre-netsh-registry-monitoring)

Returns the content of the key HKLM\_SOFTWARE\_Microsoft\_Netsh \- ATT\&CK T1128,S0108

[Read more](https://fleetdm.com/reports/mitre-netsh-registry-monitoring)  
[**MITRE \- Services Registry Monitoring**](https://fleetdm.com/reports/mitre-services-registry-monitoring)

Returns the content of the key HKLM\_SYSTEM\_CurrentControlSet\_Service \- ATT\&CK T1058

[Read more](https://fleetdm.com/reports/mitre-services-registry-monitoring)  
[**MITRE \- HKU Run Registry Monitoring**](https://fleetdm.com/reports/mitre-hku-run-registry-monitoring)

Returns the content of the key HKU\_Software\_Microsoft\_Windows\_CurrentVersion\_Run

[Read more](https://fleetdm.com/reports/mitre-hku-run-registry-monitoring)  
[**MITRE \- InstallUtil Execution**](https://fleetdm.com/reports/mitre-install-util-execution)

InstallUtil Execute, InstallUtil is a command-line utility that allows for installation and uninstallation of resources by executing specific installer components specified in .NET binaries \- ATT\&CK T1118

[Read more](https://fleetdm.com/reports/mitre-install-util-execution)  
[**MITRE \- PsExec Execution**](https://fleetdm.com/reports/mitre-ps-exec-execution)

PsExec Execute, is a free Microsoft tool that can be used to execute a program on another computer. \- ATT\&CK T1035,S0029

[Read more](https://fleetdm.com/reports/mitre-ps-exec-execution)  
[**MITRE \- Prefetch File Monitoring**](https://fleetdm.com/reports/mitre-prefetch-file-monitoring)

Monitor Windows Prefetch directory for execution artifacts \- ATT\&CK T1107

[Read more](https://fleetdm.com/reports/mitre-prefetch-file-monitoring)  
[**MITRE \- Task Scheduling**](https://fleetdm.com/reports/mitre-task-scheduling)

Schtasks Execute, usually used to create a scheduled task \- ATT\&CK T1053,S0110

[Read more](https://fleetdm.com/reports/mitre-task-scheduling)  
[**MITRE \- File Attribute Modification**](https://fleetdm.com/reports/mitre-file-attribute-modification)

Attrib Execute, usually used to modify file attributes \- ATT\&CK T1158

[Read more](https://fleetdm.com/reports/mitre-file-attribute-modification)  
[**MITRE \- BITS Transfer**](https://fleetdm.com/reports/mitre-bits-transfer)

Bitsadmin Execute, Windows Background Intelligent Transfer Service (BITS) is a low-bandwidth, asynchronous file transfer mechanism exposed through Component Object Model (COM) \- ATT\&CK T1197,S0190

[Read more](https://fleetdm.com/reports/mitre-bits-transfer)  
[**MITRE \- Certificate Utility**](https://fleetdm.com/reports/mitre-certificate-utility)

Monitor usage of Certutil.exe, a built-in command-line program to manage certificates that can be misused for malicious purposes \- ATT\&CK T1105,T1140,T1130,S0160

[Read more](https://fleetdm.com/reports/mitre-certificate-utility)  
[**MITRE \- Command Line Interface**](https://fleetdm.com/reports/mitre-command-line-interface)

Command-Line Interface Execute, CMD execution \- ATT\&CK T1059

[Read more](https://fleetdm.com/reports/mitre-command-line-interface)  
[**MITRE \- Connection Manager Profile**](https://fleetdm.com/reports/mitre-connection-manager-profile)

CMSTP Execute, The Microsoft Connection Manager Profile Installer (CMSTP.exe) is a command-line program used to install Connection Manager service profiles. \- ATT\&CK T1191

[Read more](https://fleetdm.com/reports/mitre-connection-manager-profile)  
[**MITRE \- Script Execution**](https://fleetdm.com/reports/mitre-script-execution)

Command-Line Interface Execute, Cscript execution starts a script so that it runs in a command-line environment. \- ATT\&CK T1216

[Read more](https://fleetdm.com/reports/mitre-script-execution)  
[**MITRE \- Database Utility**](https://fleetdm.com/reports/mitre-database-utility)

Monitor usage of Esentutl, a built-in command-line program that can be used to copy NTDS.dit and dump Active Directory credentials \- ATT\&CK T1003.003

[Read more](https://fleetdm.com/reports/mitre-database-utility)  
[**MITRE \- HTML Application**](https://fleetdm.com/reports/mitre-html-application)

Mshta Execute, is a utility that executes Microsoft HTML Applications (HTA) \- ATT\&CK T1170

[Read more](https://fleetdm.com/reports/mitre-html-application)  
[**MITRE \- Remote Desktop**](https://fleetdm.com/reports/mitre-remote-desktop)

mstsc.exe Execute, usually used to perform a RDP Session \- ATT\&CK T1076

[Read more](https://fleetdm.com/reports/mitre-remote-desktop)  
[**MITRE \- Network Commands**](https://fleetdm.com/reports/mitre-network-commands)

Net Execute, is used in command-line operations for control of users, groups, services, and network connections \- ATT\&CK T1126,T1087,T1201,T1069,S0039,T1018,T1007,T1124

[Read more](https://fleetdm.com/reports/mitre-network-commands)  
[**MITRE \- Network Shell**](https://fleetdm.com/reports/mitre-network-shell)

Netsh Execute, Netsh.exe (also referred to as Netshell) is a command-line scripting utility used to interact with the network configuration of a system \- ATT\&CK T1128,T1063,S0108

[Read more](https://fleetdm.com/reports/mitre-network-shell)  
[**MITRE \- Network Statistics**](https://fleetdm.com/reports/mitre-network-statistics)

Netstat Execute, is an operating system utility that displays active TCP connections, listening ports, and network statistics. \- ATT\&CK T1049,S0104

[Read more](https://fleetdm.com/reports/mitre-network-statistics)  
[**MITRE \- PowerShell Execution**](https://fleetdm.com/reports/mitre-power-shell-execution)

POWERSHELL Execute, is a powerful interactive command-line interface and scripting environment included in the Windows operating system \- ATT\&CK T1086

[Read more](https://fleetdm.com/reports/mitre-power-shell-execution)  
[**MITRE \- Registry Modification**](https://fleetdm.com/reports/mitre-registry-modification)

Reg Execute, Reg is a Windows utility used to interact with the Windows Registry. \- ATT\&CK T1214,T1012,T1063,S0075

[Read more](https://fleetdm.com/reports/mitre-registry-modification)  
[**MITRE \- Registry Editor**](https://fleetdm.com/reports/mitre-registry-editor)

Regedit Execute, is a Windows utility used to interact with the Windows Registry. \- ATT\&CK T1214

[Read more](https://fleetdm.com/reports/mitre-registry-editor)  
[**MITRE \- DLL Registration**](https://fleetdm.com/reports/mitre-dll-registration)

Detect regsvr32 DLL registration activity via prefetch artifacts \- ATT\&CK T1117

[Read more](https://fleetdm.com/reports/mitre-dll-registration)  
[**MITRE \- Privilege Escalation**](https://fleetdm.com/reports/mitre-privilege-escalation)

Runas Execute, Allows a user to run specific tools and programs with different permissions than the user's current logon provides. \- ATT\&CK T1134

[Read more](https://fleetdm.com/reports/mitre-privilege-escalation)  
[**MITRE \- Service Control**](https://fleetdm.com/reports/mitre-service-control)

SC.exe Execute, Service Control \- Create, Start, Stop, Query or Delete any Windows SERVICE. . \- ATT\&CK T1007

[Read more](https://fleetdm.com/reports/mitre-service-control)  
[**MITRE \- Scheduled Tasks Prefetch**](https://fleetdm.com/reports/mitre-scheduled-tasks-prefetch)

Schtasks Execute, usually used to create a scheduled task \- ATT\&CK T1053,S0111

[Read more](https://fleetdm.com/reports/mitre-scheduled-tasks-prefetch)  
[**MITRE \- Anomalous Svchost**](https://fleetdm.com/reports/mitre-anomalous-svchost)

SVCHOST Processes not using the \-k \[name\] convention

[Read more](https://fleetdm.com/reports/mitre-anomalous-svchost)  
[**MITRE \- System Information via Systeminfo**](https://fleetdm.com/reports/mitre-system-information-via-systeminfo)

Systeminfo Execute, Systeminfo is a Windows utility that can be used to gather detailed information about a computer. \- ATT\&CK T1082,S0096

[Read more](https://fleetdm.com/reports/mitre-system-information-via-systeminfo)  
[**MITRE \- Task Engine**](https://fleetdm.com/reports/mitre-task-engine)

taskeng Execute, usually used to create a scheduled task \- ATT\&CK T1053

[Read more](https://fleetdm.com/reports/mitre-task-engine)  
[**MITRE \- Process Termination**](https://fleetdm.com/reports/mitre-process-termination)

Taskkill Execute, usually used to kill task

[Read more](https://fleetdm.com/reports/mitre-process-termination)  
[**MITRE \- Process Enumeration**](https://fleetdm.com/reports/mitre-process-enumeration)

Tasklist Execute, usually used to list task \- ATT\&CK T1057,T1063,T1007,S0057

[Read more](https://fleetdm.com/reports/mitre-process-enumeration)  
[**MITRE \- Terminal Services**](https://fleetdm.com/reports/mitre-terminal-services)

tscon.exe Execute, usually used to Terminal Services Console \- ATT\&CK T1076

[Read more](https://fleetdm.com/reports/mitre-terminal-services)  
[**MITRE \- Volume Shadow Copy**](https://fleetdm.com/reports/mitre-volume-shadow-copy)

Vssadmin Execute, usually used to execute activity on Volume Shadow copy

[Read more](https://fleetdm.com/reports/mitre-volume-shadow-copy)  
[**MITRE \- User Identification**](https://fleetdm.com/reports/mitre-user-identification)

Whoami Execute, used to prints the effective username of the current user

[Read more](https://fleetdm.com/reports/mitre-user-identification)  
[**MITRE \- File Copy**](https://fleetdm.com/reports/mitre-file-copy)

Xcopy Execute, is used for copying multiple files or entire directory trees from one directory to another and for copying files across a network.

[Read more](https://fleetdm.com/reports/mitre-file-copy)  
[**MITRE \- Chrome Extensions Snapshot**](https://fleetdm.com/reports/mitre-chrome-extensions-snapshot)

Snapshot Lists all chrome extensions \- ATT\&CK T1176

[Read more](https://fleetdm.com/reports/mitre-chrome-extensions-snapshot)  
[**MITRE \- Internet Explorer Extensions Snapshot**](https://fleetdm.com/reports/mitre-internet-explorer-extensions-snapshot)

Snapshot Lists all internet explorer extensions \- ATT\&CK T1176

[Read more](https://fleetdm.com/reports/mitre-internet-explorer-extensions-snapshot)  
[**MITRE \- Internet Explorer Extensions**](https://fleetdm.com/reports/mitre-internet-explorer-extensions)

Lists all internet explorer extensions \- ATT\&CK T1176

[Read more](https://fleetdm.com/reports/mitre-internet-explorer-extensions)  
[**MITRE \- Sophos Service Status 1**](https://fleetdm.com/reports/mitre-sophos-service-status-1)

Sophos Endpoint Protection service status change \- ATT\&CK T1089

[Read more](https://fleetdm.com/reports/mitre-sophos-service-status-1)  
[**MITRE \- Services Snapshot**](https://fleetdm.com/reports/mitre-services-snapshot)

Snapshot Services query

[Read more](https://fleetdm.com/reports/mitre-services-snapshot)  
[**MITRE \- Sophos Service Status 2**](https://fleetdm.com/reports/mitre-sophos-service-status-2)

Sophos Endpoint Protection service status change \- ATT\&CK T1089

[Read more](https://fleetdm.com/reports/mitre-sophos-service-status-2)  
[**MITRE \- Symantec Service Status**](https://fleetdm.com/reports/mitre-symantec-service-status)

Symantec Endpoint Protection service status change \- ATT\&CK T1089

[Read more](https://fleetdm.com/reports/mitre-symantec-service-status)  
[**MITRE \- Windows Defender Service Status**](https://fleetdm.com/reports/mitre-windows-defender-service-status)

Windows Defender service Status change \- ATT\&CK T1089

[Read more](https://fleetdm.com/reports/mitre-windows-defender-service-status)  
[**MITRE \- Windows Firewall Service Status**](https://fleetdm.com/reports/mitre-windows-firewall-service-status)

Windows Firewall service Status change \- ATT\&CK T1089

[Read more](https://fleetdm.com/reports/mitre-windows-firewall-service-status)  
[**MITRE \- Windows Security Service Status**](https://fleetdm.com/reports/mitre-windows-security-service-status)

Windows Security Service Status change \- ATT\&CK T1089

[Read more](https://fleetdm.com/reports/mitre-windows-security-service-status)  
[**MITRE \- Windows Update Service Status**](https://fleetdm.com/reports/mitre-windows-update-service-status)

Windows Update Service Status change \- ATT\&CK T1089

[Read more](https://fleetdm.com/reports/mitre-windows-update-service-status)  
[**MITRE \- Certificate Discovery**](https://fleetdm.com/reports/mitre-certificate-discovery)

Discover local system certificates for code signing and trust chain analysis \- ATT\&CK T1116,T1130

[Read more](https://fleetdm.com/reports/mitre-certificate-discovery)  
[**MITRE \- Installed Programs**](https://fleetdm.com/reports/mitre-installed-programs)

Lists installed programs on Windows systems \- ATT\&CK T1518

[Read more](https://fleetdm.com/reports/mitre-installed-programs)  
[**MITRE \- System Info Snapshot**](https://fleetdm.com/reports/mitre-system-info-snapshot)

System information for identification.

[Read more](https://fleetdm.com/reports/mitre-system-info-snapshot)  
[**MITRE \- System Uptime**](https://fleetdm.com/reports/mitre-system-uptime)

System uptime

[Read more](https://fleetdm.com/reports/mitre-system-uptime)  
[**MITRE \- Windows Crash Analysis**](https://fleetdm.com/reports/mitre-windows-crash-analysis)

Extracted information from Windows crash logs (Minidumps).

[Read more](https://fleetdm.com/reports/mitre-windows-crash-analysis)  
[**MITRE \- AppData Local Directory Creation**](https://fleetdm.com/reports/mitre-app-data-local-directory-creation)

Check suspicious directory creation under AppData\\Local \- ATT\&CK T1034,T1074,T1044

[Read more](https://fleetdm.com/reports/mitre-app-data-local-directory-creation)  
[**MITRE \- AppData Temp Directory Creation**](https://fleetdm.com/reports/mitre-app-data-temp-directory-creation)

Check suspicious directory creation under %TEMP% or AppData\\Local\\Temp \- ATT\&CK T1034,T1074,T1044

[Read more](https://fleetdm.com/reports/mitre-app-data-temp-directory-creation)  
[**MITRE \- AppData Roaming Directory Creation**](https://fleetdm.com/reports/mitre-app-data-roaming-directory-creation)

Check suspicious directory creation under %APPDATA% or %\\AppData\\Roaming \- ATT\&CK T1034,T1074,T1044

[Read more](https://fleetdm.com/reports/mitre-app-data-roaming-directory-creation)  
[**MITRE \- User Start Menu Program Directory Creation**](https://fleetdm.com/reports/mitre-user-start-menu-program-directory-creation)

Check suspicious directory creation under Roaming\\Microsoft\\Windows\\Start Menu\\Programs \- ATT\&CK T1060,T1023

[Read more](https://fleetdm.com/reports/mitre-user-start-menu-program-directory-creation)  
[**MITRE \- User Start Menu Startup Directory Creation**](https://fleetdm.com/reports/mitre-user-start-menu-startup-directory-creation)

Check suspicious directory creation under Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup \- ATT\&CK T1060,T1023

[Read more](https://fleetdm.com/reports/mitre-user-start-menu-startup-directory-creation)  
[**MITRE \- ProgramData Start Menu Directory Creation**](https://fleetdm.com/reports/mitre-program-data-start-menu-directory-creation)

Check suspicious directory creation under ProgramData\\Microsoft\\Windows\\Start Menu \- ATT\&CK T1060,T1023

[Read more](https://fleetdm.com/reports/mitre-program-data-start-menu-directory-creation)  
[**MITRE \- ProgramData Start Menu Program Directory Creation**](https://fleetdm.com/reports/mitre-program-data-start-menu-program-directory-creation)

Check suspicious directory creation under ProgramData\\Microsoft\\Windows\\Start Menu\\Programs \- ATT\&CK T1060,T1023

[Read more](https://fleetdm.com/reports/mitre-program-data-start-menu-program-directory-creation)  
[**MITRE \- Windows Directory Creation**](https://fleetdm.com/reports/mitre-windows-directory-creation)

Check suspicious directory creation under c:\\windows \- ATT\&CK T1034,T1074,T1044

[Read more](https://fleetdm.com/reports/mitre-windows-directory-creation)  
[**MITRE \- Windows Temp Directory Creation**](https://fleetdm.com/reports/mitre-windows-temp-directory-creation)

Check suspicious directory creation under c:\\windows emp \- ATT\&CK T1034,T1074,T1044

[Read more](https://fleetdm.com/reports/mitre-windows-temp-directory-creation)  
[**MITRE \- AppData Local File Creation**](https://fleetdm.com/reports/mitre-app-data-local-file-creation)

Check suspicious file creation under AppData\\Local \- ATT\&CK T1034,T1074,T1044

[Read more](https://fleetdm.com/reports/mitre-app-data-local-file-creation)  
[**MITRE \- AppData Temp File Creation**](https://fleetdm.com/reports/mitre-app-data-temp-file-creation)

Check suspicious file creation under %TEMP% or AppData\\Local\\Temp \- ATT\&CK T1034,T1074,T1044

[Read more](https://fleetdm.com/reports/mitre-app-data-temp-file-creation)  
[**MITRE \- AppData Roaming File Creation**](https://fleetdm.com/reports/mitre-app-data-roaming-file-creation)

Check suspicious file creation under %APPDATA% or %\\AppData\\Roaming \- ATT\&CK T1034,T1074,T1044

[Read more](https://fleetdm.com/reports/mitre-app-data-roaming-file-creation)  
[**MITRE \- ProgramData Start Menu File Creation**](https://fleetdm.com/reports/mitre-program-data-start-menu-file-creation)

Check suspicious file creation under ProgramData\\Microsoft\\Windows\\Start Menu \- ATT\&CK T1060,T1023

[Read more](https://fleetdm.com/reports/mitre-program-data-start-menu-file-creation)  
[**MITRE \- ProgramData Start Menu Program File Creation**](https://fleetdm.com/reports/mitre-program-data-start-menu-program-file-creation)

Check suspicious file creation under ProgramData\\Microsoft\\Windows\\Start Menu\\Programs \- ATT\&CK T1060,T1023

[Read more](https://fleetdm.com/reports/mitre-program-data-start-menu-program-file-creation)  
[**MITRE \- User Start Menu Program File Creation**](https://fleetdm.com/reports/mitre-user-start-menu-program-file-creation)

Check suspicious file creation under Roaming\\Microsoft\\Windows\\Start Menu\\Programs \- ATT\&CK T1060,T1023

[Read more](https://fleetdm.com/reports/mitre-user-start-menu-program-file-creation)  
[**MITRE \- User Start Menu Startup File Creation**](https://fleetdm.com/reports/mitre-user-start-menu-startup-file-creation)

Check suspicious file creation under Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup \- ATT\&CK T1060,T1023

[Read more](https://fleetdm.com/reports/mitre-user-start-menu-startup-file-creation)  
[**MITRE \- Windows File Creation**](https://fleetdm.com/reports/mitre-windows-file-creation)

Check suspicious file creation under c:\\windows \- ATT\&CK T1034,T1074,T1044

[Read more](https://fleetdm.com/reports/mitre-windows-file-creation)  
[**MITRE \- Windows Temp File Creation**](https://fleetdm.com/reports/mitre-windows-temp-file-creation)

Check suspicious file creation under c:\\windows emp \- ATT\&CK T1034,T1074,T1044

[Read more](https://fleetdm.com/reports/mitre-windows-temp-file-creation)  
[**MITRE \- Startup Items**](https://fleetdm.com/reports/mitre-startup-items)

Startup items configured to launch on the system \- ATT\&CK T1060

[Read more](https://fleetdm.com/reports/mitre-startup-items)  
[**MITRE \- PowerShell Script Block Events**](https://fleetdm.com/reports/mitre-power-shell-script-block-events)

Powershell script blocks reconstructed to their full script content, this table requires script block logging to be enabled. \- ATT\&CK T1086,T1064

[Read more](https://fleetdm.com/reports/mitre-power-shell-script-block-events)  
[**MITRE \- Fileless Process Detection**](https://fleetdm.com/reports/mitre-fileless-process-detection)

Detect Processes running without a binary on disk

[Read more](https://fleetdm.com/reports/mitre-fileless-process-detection)  
[**MITRE \- Scheduled Tasks List**](https://fleetdm.com/reports/mitre-scheduled-tasks-list)

Lists all of the tasks in the Windows task scheduler \- ATT\&CK T1053

[Read more](https://fleetdm.com/reports/mitre-scheduled-tasks-list)  
[**MITRE \- Auto-Start Services**](https://fleetdm.com/reports/mitre-auto-start-services)

Lists all installed services configured to start automatically at boot \- ATT\&CK T1050

[Read more](https://fleetdm.com/reports/mitre-auto-start-services)  
[**MITRE \- Running Processes**](https://fleetdm.com/reports/mitre-running-processes)

List running processes with path and command line. \- ATT\&CK T1034,T1121,T1117,T1085

[Read more](https://fleetdm.com/reports/mitre-running-processes)  
