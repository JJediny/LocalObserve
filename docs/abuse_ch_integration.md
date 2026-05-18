# Abuse.ch Threat Intelligence Integration

This document explains the data provided by Abuse.ch (MalwareBazaar, URLhaus, etc.), how the automated download process works, and how to best integrate these datasets with OpenObserve, ClamAV, and osquery.

## The Datasource: Abuse.ch

Abuse.ch maintains several high-quality, community-driven threat intelligence platforms:
1. **MalwareBazaar**: A repository of malware samples, YARA rules, and indicators of compromise (IoCs).
2. **URLhaus**: A platform focusing on tracking malware distribution URLs.
3. **CSCB (Code Signing Certificate Blocklist)**: A list of certificates used by threat actors to sign malicious binaries.

### Authentication
As of recent updates, downloading bulk datasets from Abuse.ch via their v2 API requires an **Auth-Key**. 
- The Auth-Key is associated with an Abuse.ch account.
- It is passed as a URL parameter: `https://mb-api.abuse.ch/v2/files/exports/YOUR-AUTH-KEY-HERE/...`
- In this environment, the key is securely stored in `.env` as `ABUSE_CH_AUTH_KEY`.

---

## The Download Process

The script located at `tools/update_yara_rules.sh` automates the ingestion of YARA rules and other datasets:
1. **Authentication**: It securely reads `ABUSE_CH_AUTH_KEY` from `.env`.
2. **Fetching Data**: It queries the Abuse.ch API endpoints for the latest datasets (e.g., recent CSVs, YARA rule exports).
3. **Staging**: It places the downloaded `.yar` files into mapped volumes accessible by both ClamAV and osquery.
4. **Reloading**: It instructs ClamAV to dynamically reload its signature databases.

You should run this script via a `cron` job or a dedicated sidecar container once every 24 hours to ensure your detection rules are up to date.

---

## Integration Suggestions

### 1. ClamAV Integration

**Native YARA Support:**
ClamAV has built-in support for parsing and evaluating YARA rules. 
- You simply need to place `.yara` or `.yar` files in ClamAV's database directory (`/var/lib/clamav`).
- **Optimization**: By mapping a persistent volume (`clamav_db`) to your host, the `update_yara_rules.sh` script can download the rules directly into the volume.
- **Reloading**: Run `clamdscan --reload` (or rely on `ConcurrentDatabaseReload` in `clamd.conf`) to immediately apply new YARA rules without dropping the daemon.

### 2. OSquery Integration

**Configuring YARA in OSquery:**
osquery features a powerful `yara` table that allows scanning files on-demand or during filesystem events (FIM).

1. **osquery.conf Configuration**:
   Map the downloaded YARA rules to signature groups in your configuration:
   ```json
   {
     "yara": {
       "signatures": {
         "abuse_ch": [ "/var/log/osquery/yara/abuse_ch.yar" ]
       }
     }
   }
   ```

2. **On-Demand Scanning**:
   Query suspicious directories manually:
   ```sql
   SELECT * FROM yara WHERE path LIKE '/tmp/%%' AND siggroup = 'abuse_ch';
   ```

3. **Event-Based Scanning (FIM + YARA)**:
   Configure the `yara_events` table so osquery automatically evaluates downloaded files against the Abuse.ch rules in real-time.

### 3. OpenObserve Integration

To close the loop, you must funnel the detection events from ClamAV and osquery into OpenObserve.

1. **Log Parsing**:
   Ensure your OpenTelemetry Collector is configured to parse ClamAV and osquery logs. For ClamAV, a regex parser can extract the `FOUND` status and the matching YARA rule name.
   
2. **Dashboards**:
   Create a "Threat Detection" dashboard in OpenObserve that tracks:
   - File paths most commonly flagged by YARA rules.
   - A time-series chart of detections to identify spikes in malicious activity.
   - Breakdown of hits by specific Abuse.ch YARA rules to identify the malware families targeting your infrastructure.

3. **Alerting**:
   Set up an alert in OpenObserve based on the parsed logs.
   - **Condition**: `log.source = 'clamav' AND status = 'FOUND'` OR `log.source = 'osquery' AND yara_matches != ''`.
   - **Action**: Trigger a webhook to a Slack channel or an incident management tool to alert the security team immediately.
