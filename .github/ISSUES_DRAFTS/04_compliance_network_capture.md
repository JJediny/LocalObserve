# compliance: Network capture controls, minimization, and retention

### Source
White House OMB Memorandum M-26-14, Appendix A and Appendix B.5.b.

### Extracted Requirement
> *"The LRA will include guidance to ensure that logs will not capture or expose data in contravention of law. It will also advise agencies on how to protect the confidentiality and integrity of sensitive log data... At a minimum, agencies must collect logs that support...: b. Determining source and destination network address information, including protocols, ports, and session attributes."*

### Suggested Tasks
1. Complete the docker-compose integration of `openobserve/goflow2` to capture structured sFlow/NetFlow/IPFIX logs.
2. Develop high-efficiency collector regex filters to purge incidental payload fields containing potentially sensitive PII or data in contravention of privacy laws.
3. Configure KMS encryption keys and standard TLS 1.3 tunnels for all network capture log transit paths.

### Acceptance Criteria
- GoFlow2 integrates smoothly within the compose orchestrator, emitting structured network connection logs.
- Test logs demonstrate successful filtering and stripping of payload details while retaining required IP, port, protocol, and session attributes.
- Network log data retention configurations map to the 12-month THIRF requirements.
