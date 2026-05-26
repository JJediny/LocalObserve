# compliance: Log retention and secure archival policy

### Source
White House OMB Memorandum M-26-14, Appendix B.1 and Appendix C.

### Extracted Requirement
> *"Retained logs must be actively searchable for a minimum of 6 months after creation to support continuous event monitoring (CEM). They must be retrievable for a year after creation to support threat-hunting, investigation, response, and forensics (THIRF)..."*

### Suggested Tasks
1. Configure OpenObserve retention policies to retain hot/active logging datasets for at least 180 days (6 months).
2. Configure long-term cold storage lifecycles (e.g. S3 glacier, local gzip archives) to securely retain and index logs up to 365 days (12 months).
3. Draft clear recovery playbooks detailing cold-log "thawing" procedures to restore archived telemetry back to active searchable analysis tiers during threat-hunting operations.

### Acceptance Criteria
- Storage configuration parameters explicitly map to the 6-month hot searchable and 12-month cold retrieval baseline.
- Automated tests or staging scripts verify that log data past the 180-day window is successfully rolled to archival storage and not deleted prematurely.
- Archival extraction and "thawing" procedures are fully documented under `docs/compliance.md`.
