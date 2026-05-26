### Summary
This Pull Request introduces the foundational **M-26-14 Compliance Crosswalk** and corresponding GitHub Issue Drafts mapping OMB M-26-14 federal logging requirements in the **LocalObserve** pipeline.

### What this PR does
1. **M-26-14 Crosswalk Document**: Creates `docs/compliance_crosswalk.md` mapping M-26-14 requirements for real-time Continuous Event Monitoring (CEM) and Threat Hunting, Investigation, Response, and Forensics (THIRF) to specific architectural features in LocalObserve, fully linked to active tracking issues.
2. **Standardized Issue Drafts**: Adds 8 per-requirement GitHub Issue Drafts inside `.github/ISSUES_DRAFTS/` containing exact text extractions, suggested tasks, and verification acceptance criteria.
3. **Tracking Integration**: Programmatically creates all 8 compliance tracking issues (Issues #19 to #26) on the GitHub repository and links them directly inside the crosswalk table and detailed requirement sections.
