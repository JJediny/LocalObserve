# compliance: Centralized structured logging for all components

### Source
White House OMB Memorandum M-26-14, Appendix B.2, B.3, and B.5.

### Extracted Requirement
> *"Logs must include a consistently accurate timestamp. To ensure accuracy, network time must be synchronized to Network Time Protocol (NTP) or equivalent mechanisms to a traceable time source designated within the agency. Agencies are encouraged to use authoritative time sources traceable to the U.S. Naval Observatory or the National Institute of Standards (NIST)... At a minimum, agencies must collect logs that support...: a. Determining the identity used for performing operations... b. Determining source and destination network address... c. Identifying object/resource/data events... d. Identifying actions that affect changes to privilege levels."*

### Suggested Tasks
1. Ensure all LocalObserve collector/agent components (`otelcol`, `osqueryd`, `falco`) serialize log payloads to standard structured JSON format.
2. Synchronize all Docker host environments and collector runtime nodes via NTP against authoritative servers.
3. Validate that standard JSON schemas consistently include crucial tracking fields: UTC timestamp, component identifier, severity/priority, user/session identifier, and network metadata (source/destination IP, port, protocol).

### Acceptance Criteria
- All system collectors emit fully structured, standardized JSON logs at `INFO+` levels.
- Verification tests exist in CI to validate the presence of mandatory structural logging fields.
- Logging architecture and schema documentation are fully updated in the repository.
