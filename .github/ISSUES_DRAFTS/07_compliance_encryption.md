# compliance: Data protection for stored log and capture artifacts (encryption & KMS)

### Source
White House OMB Memorandum M-26-14, Appendix C (Log Management Level 2 & 3).

### Extracted Requirement
> *"Logs are stored and encrypted at rest... Logs are encrypted in transit and at rest, and regularly hashed for veracity."*

### Suggested Tasks
1. Enforce TLS 1.3 encryption across all internal log routing paths (`otelcol` to OpenObserve).
2. Configure AES-256 at-rest encryption on the primary OpenObserve storage tier.
3. Establish a standard policy and key rotation schedule for storage encryption keys using an integrated Key Management Service (KMS).

### Acceptance Criteria
- Configuration files explicitly reference TLS 1.3 and active KMS-backed at-rest encryption setups.
- Compliance test files confirm that unauthenticated users cannot read stored data partitions.
- Security key rotation policy is fully documented in the compliance baseline files.
