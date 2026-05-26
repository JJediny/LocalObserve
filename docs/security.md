# Security

## Scope

This repository contains local monitoring configuration, scripts, and documentation for a lightweight Linux monitoring setup.

It is currently best treated as a local evaluation and experimentation project, not a production-hardened security product.

## Reporting a security issue

If you believe you found a security issue in the repository contents, please report it privately to the project maintainer rather than opening a public issue immediately.

Until a formal project contact process exists, do not publish sensitive details, credentials, or exploit instructions directly in a public bug report.

## Good-faith expectations

When reporting an issue, include:

- what file or behavior is affected
- why you believe it is security-relevant
- how it can be reproduced
- what the practical impact is in a local deployment

## Current support boundaries

The following are important project boundaries:

- default credentials and local-only assumptions exist for ease of evaluation and should not be treated as production-safe defaults
- Falco behavior on Docker Desktop or LinuxKit-style environments is currently environment-limited
- host integration scripts may assume Linux and systemd
- the repository is optimized for low-write local monitoring rather than full enterprise hardening

## What is especially sensitive in this repository

Be careful not to expose:

- local `.env` files
- generated `.data/` contents
- host-specific credentials or tokens
- personally identifying machine details that may appear in copied logs or screenshots

The repository `.gitignore` is configured to avoid committing common generated data and local credentials, but you should still review changes carefully before publishing them.

---

## Data Protection & Encryption Compliance (OMB M-26-14 Req-7)

To comply with Level 2/3 Log Management requirements under **OMB Memorandum M-26-14**, all collected security logs, network captures, and auditing artifacts must be strictly protected using enterprise-grade cryptographic controls in transit and at rest.

### 1. In-Transit Encryption (TLS 1.3)
All log transmission pipelines (OTel Collector -> OpenObserve, GoFlow2 -> OTel Collector) must enforce **TLS 1.3** to protect against passive wiretapping and active credential harvesting. 

To configure strict OTel Collector in-transit encryption, configure the `exporters` TLS block as follows:
```yaml
exporters:
  otlp_http/openobserve_secure:
    endpoint: https://openobserve.agency.gov:5080/api/default
    auth:
      authenticator: basicauth/openobserve
    tls:
      insecure: false
      min_version: "1.3"
      cipher_suites:
        - TLS_AES_256_GCM_SHA384
        - TLS_CHACHA20_POLY1305_SHA256
```

### 2. At-Rest Encryption (AES-256-GCM)
Primary log storage volumes, database chunks, and metadata must be encrypted at rest using **AES-256-GCM**.
Inside OpenObserve, at-rest encryption is managed via local storage configuration or AWS S3 Server-Side Encryption (SSE-S3 / SSE-KMS). 

To enable strict local at-rest encryption in OpenObserve, append the following environment variables to the service in `docker-compose.yaml`:
```yaml
services:
  openobserve:
    environment:
      - ZO_ENCRYPTION_KEY=${ZO_LOG_ENCRYPTION_KEY} # Must be a 32-byte cryptographically secure key
      - ZO_LOCAL_STRICT_AES_DECRYPT=true
```

### 3. Key Management Service (KMS) & Key Rotation Schedule
To guarantee cryptographic integrity and minimize exposure in the event of compromised credentials, the master key must be managed via an authoritative KMS (such as AWS KMS, HashiCorp Vault, or Google Cloud KMS) under the following rotation schedule:

| Key Type | Cryptographic Algorithm | Rotation Frequency | Standards Compliance |
| :--- | :--- | :--- | :--- |
| **Log Ingestion Master Key** | AES-256-GCM | Every 90 Days | NIST SP 800-57 Part 1 |
| **OTel Collector Basic Auth Token** | SHA-256 PBKDF2 | Every 60 Days | OMB M-26-14 Baseline |
| **KMS Root Wrapping Key (KEK)** | RSA-4096 / ECDSA P-384 | Annually | FIPS 140-3 Level 3 |

*   **Rotation Execution:** Key rotation is performed dynamically via KMS without interrupting active log streams. Old keys are archived to decrypt legacy storage blocks, while new writes are wrapped with the newly rotated key.

