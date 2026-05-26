# M-26-14 Logging Compliance Crosswalk & Audit

This document establishes the official compliance crosswalk for the **LocalObserve** project against the White House Office of Management and Budget (OMB) Memorandum **M-26-14**: *Ensuring Effective and Efficient Agency Logging and Network Visibility to Defend Against Evolving Cyber Threats* (published May 22, 2026).

## Executive Summary
OMB Memorandum M-26-14 rescinded M-21-31 to implement an adaptive, risk-prioritized framework that balances network observability and incident response with operational feasibility and cost effectiveness. It focuses on two core logging objectives:
1. **Continuous Event Monitoring (CEM)**: Real-time telemetry ingestion and analysis for immediate security monitoring.
2. **Threat Hunting, Investigation, Response, and Forensics (THIRF)**: Cold/hot data storage and retrieval capabilities for deep post-incident tracing.

This audit crosswalk maps M-26-14 baseline mandates to specific architectural objectives, issue trackers, and technical parameters in LocalObserve.

---

## Logging Compliance Audit Matrix

| Req ID | M-26-14 Target Reference | LocalObserve Implementation Strategy | Tracking Issue | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Req-1** | Appendix B.3, B.5 (Structured Schema & Timestamp Sync) | JSON-structured log formatting across all system collectors, aligned with authoritative, agency-approved NTP synchronization. | [Issue #19](https://github.com/JJediny/LocalObserve/issues/19) | 🟢 Completed |
| **Req-2** | Appendix B.1 (Retention Policy: Search vs. Retrieval) | 6-month hot searchable data retention in OpenObserve alongside a 12-month cold retrieval policy. | [Issue #20](https://github.com/JJediny/LocalObserve/issues/20) | 🟢 Completed |
| **Req-3** | Par. 125-131, Appendix C (Access Controls & JIT) | SOC integration, Just-In-Time (JIT) access policies, and audited log exports for CISA/FBI. | [Issue #21](https://github.com/JJediny/LocalObserve/issues/21) | 🟡 Planned |
| **Req-4** | Appendix A, B.5.b (Network Capture Minimization) | Integrated flow captures via `goflow2` with PII filters to protect sensitive identifiers. | [Issue #22](https://github.com/JJediny/LocalObserve/issues/22) | 🟡 Planned |
| **Req-5** | Appendix C (Log Veracity & Hashing) | Cryptographically chain-linked SHA-256 audit ledger verification for telemetry configurations. | [Issue #23](https://github.com/JJediny/LocalObserve/issues/23) | 🟢 Completed |
| **Req-6** | Appendix B.5.k, Appendix C (Pipeline Monitoring & Alerts) | Pipeline health monitoring, threshold alerting for data drops, and tuning alerts. | [Issue #24](https://github.com/JJediny/LocalObserve/issues/24) | 🟡 Planned |
| **Req-7** | Appendix C (Data Protection & KMS) | TLS 1.3 transit encryption, AES-256 at-rest encryption, and integration with KMS. | [Issue #25](https://github.com/JJediny/LocalObserve/issues/25) | 🟡 Planned |
| **Req-8** | Appendix A, C (Compliance Validation & CI) | Automated CI regression tests verifying compliance controls and fields. | [Issue #26](https://github.com/JJediny/LocalObserve/issues/26) | 🟢 Completed |

---

## Detailed Compliance Requirements

### Requirement 1: Centralized Structured Logging for all Components
- **M-26-14 Text Reference**: 
  > *"Log storage may be decentralized; however, logs must be readily available to the top-level agency security operations center (SOC)... Logs must include a consistently accurate timestamp. To ensure accuracy, network time must be synchronized to Network Time Protocol (NTP) or equivalent mechanisms to a traceable time source... traceable to the U.S. Naval Observatory or NIST, where feasible."* (Appendix B.2, B.3, B.5)
- **LocalObserve Implementation Plan**:
  Configure the collector (`otelcol`) and agent (`osqueryd`, `falco`) engines to append standard UTC timestamps and serialize outputs to JSON formats. Synchronize container and host systems against configurable, agency-approved NTP servers (for example, internal stratum sources or NIST-provided endpoints, where feasible).
- **Assigned Tracker**: [Issue #19](https://github.com/JJediny/LocalObserve/issues/19)

### Requirement 2: Log Retention and Secure Archival Policy
- **M-26-14 Text Reference**: 
  > *"Retained logs must be actively searchable for a minimum of 6 months after creation to support continuous event monitoring (CEM). They must be retrievable for a year after creation to support threat-hunting, investigation, response, and forensics (THIRF)."* (Appendix B.1)
- **LocalObserve Implementation Plan**:
  Enforce a tiered retention cycle in OpenObserve and backend storage: 180 days (6 months) hot searchable storage, and 365 days (1 year) compressed archival.
- **Assigned Tracker**: [Issue #20](https://github.com/JJediny/LocalObserve/issues/20)

### Requirement 3: Access Controls and RBAC for Log & Network Data
- **M-26-14 Text Reference**: 
  > *"In the event of a known or suspected compromise... provide logs and other relevant data to CISA and the Federal Bureau of Investigation (FBI) upon request... Logs are encrypted, access is granted just in time, permissions and workloads are regularly monitored and reviewed..."* (Par. 125-131, Appendix C)
- **LocalObserve Implementation Plan**:
  Introduce a Just-in-Time (JIT) access permission matrix in OpenObserve. Implement a standardized log export tool matching CISA/FBI ingestion schemas.
- **Assigned Tracker**: [Issue #21](https://github.com/JJediny/LocalObserve/issues/21)

### Requirement 4: Network Capture Controls, Minimization, and Retention
- **M-26-14 Text Reference**: 
  > *"Determining source and destination network address information, including protocols, ports, and session attributes... LRA will include guidance to ensure that logs will not capture or expose data in contravention of law. It will also advise agencies on how to protect the confidentiality and integrity of sensitive log data."* (Appendix A, Appendix B.5.b)
- **LocalObserve Implementation Plan**:
  Utilize `openobserve/goflow2` for structured NetFlow/sFlow logging. Apply regex filters at the collector layer to strip out user payloads (PII) to minimize incidental exposure.
- **Assigned Tracker**: [Issue #22](https://github.com/JJediny/LocalObserve/issues/22)

### Requirement 5: Tamper-Evident Audit Trail for Logging Pipeline & Config
- **M-26-14 Text Reference**: 
  > *"Logs are encrypted in transit and at rest, and regularly hashed for veracity."* (Appendix C - Log Management Level 3)
- **LocalObserve Implementation Plan**:
  Store logging pipeline configuration in git with strict branch protections. Compute SHA-256 hashes of rolled storage chunks and log them to a separate tamper-evident audit ledger.
- **Assigned Tracker**: [Issue #23](https://github.com/JJediny/LocalObserve/issues/23)

### Requirement 6: Monitoring, Alerting, and Incident Response Hooks for Logging Anomalies
- **M-26-14 Text Reference**: 
  > *"Generating appropriate automated alerts for all of the above... Logs generate actionable alerts covering at least 70% of baseline logging requirements, and detections are routinely evaluated and tuned."* (Appendix B.5.k, Appendix C)
- **LocalObserve Implementation Plan**:
  Deploy health monitoring alerting for `otelcol` and `OpenObserve` storage sinks. Define alerts for logging pipeline anomalies (e.g. dramatic drops in log ingestion rate).
- **Assigned Tracker**: [Issue #24](https://github.com/JJediny/LocalObserve/issues/24)

### Requirement 7: Data Protection for Stored Log & Capture Artifacts (Encryption & KMS)
- **M-26-14 Text Reference**: 
  > *"Logs are stored and encrypted at rest... Logs are encrypted in transit and at rest, and regularly hashed for veracity."* (Appendix C - Log Management Level 2 & 3)
- **LocalObserve Implementation Plan**:
  Enforce TLS 1.3 for all internal log ingestion streams. Configure AES-256 at-rest encryption inside OpenObserve backend blocks utilizing KMS integration for periodic key rotation.
- **Assigned Tracker**: [Issue #25](https://github.com/JJediny/LocalObserve/issues/25)

### Requirement 8: Documentation, Tests, and CI Checks for Compliance Controls
- **M-26-14 Text Reference**: 
  > *"Agencies must submit an Agency Logging Plan to OMB and CISA... Agencies will measure and report on progress in terms of the percentage of systems that are determined to be operating at each maturity level."* (Par. 105-121)
- **LocalObserve Implementation Plan**:
  Develop automated regression check files verifying structured JSON logging schema conformance and retention configurations in GitHub CI pipelines.
- **Assigned Tracker**: [Issue #26](https://github.com/JJediny/LocalObserve/issues/26)
