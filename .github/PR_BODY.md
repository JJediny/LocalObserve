### Summary
This Pull Request introduces the foundational **M-26-14 Compliance Crosswalk** and corresponding GitHub Issue Drafts to track the implementation of OMB M-26-14 federal logging requirements in the **LocalObserve** pipeline.

### What this PR does
1. **M-26-14 Crosswalk Document**: Creates `docs/compliance_crosswalk.md` mapping M-26-14 requirements for real-time Continuous Event Monitoring (CEM) and Threat Hunting, Investigation, Response, and Forensics (THIRF) to specific architectural features in LocalObserve.
2. **Standardized Issue Drafts**: Adds 8 per-requirement GitHub Issue Drafts inside `.github/ISSUES_DRAFTS/` containing exact text extractions, suggested tasks, and verification acceptance criteria.
3. **Programmatic Audit Preparation**: Provisions tracking placeholders to link active GitHub issue numbers once created.

### Follow-up
1. Create issues programmatically from `.github/ISSUES_DRAFTS/`.
2. Update the tracking table inside `docs/compliance_crosswalk.md` with active issue links.
