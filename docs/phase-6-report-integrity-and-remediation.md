# Phase 6 - Report Integrity and Security Remediation

## Baseline

Phase 6 begins from main after Phase 5 merge commit `2056ceed71b517b61bb21c0ba8fda522e1ae8940` and the Comprehensive report run `comprun_35f88b49648d438a86a9490c244b8046`.

The baseline report is materially improved but still exposes customer-facing truth and usability defects:

- It reports Bandit and ESLint as failed and Gitleaks and OSV Scanner as partial even though Phase 5 retained complete exact-SHA evidence.
- It repeats identical risks and findings, including duplicate stable IDs, duplicate locations, and repeated roadmap mappings.
- It promotes scanner rule prose as the executive risk title instead of a concise repository-specific decision statement.
- It reports inconsistent source locations for the same stable finding across repeated records.
- It reports `current required-check health green: False` despite the final Phase 5 matrix being green.
- Complexity output includes noisy module-region counts and does not distinguish actionable functions from generated or structural regions.
- Artifact naming can repeat terminal labels such as `FINAL-PENDING-APPROVAL`.

## Required work packages

1. **Exact-SHA evidence reconciliation**
   - Consume the retained Phase 5 scanner package from the assessed commit.
   - Prevent stale scanner states from surviving into a later report.
   - Fail closed when scanner evidence belongs to a different SHA.

2. **Canonical finding identity and deduplication**
   - Produce one canonical record per finding identity and exact location.
   - Merge duplicate evidence references without multiplying risk rows.
   - Deduplicate roadmap and backlog mappings while preserving order.
   - Detect stable-ID collisions when materially different locations share an ID.

3. **Executive risk normalization**
   - Replace raw analyzer rule prose with concise repository-specific titles.
   - Preserve the full analyzer message in the evidence layer.
   - Rank unique risks, not repeated records.

4. **Location integrity**
   - Normalize paths and line numbers once.
   - Ensure the executive register, detailed register, JSON, CSV, Markdown, HTML, and PDF use the same canonical location.

5. **CI and release truth**
   - Derive required-check health from the exact assessed commit.
   - Separate historical failures from current required-check state.
   - Never display a red current-state claim when the exact-SHA required matrix is green.

6. **Actionable complexity reporting**
   - Separate functions, methods, components, and module regions.
   - Exclude generated, vendored, fixture, and structural noise from executive hotspot counts.
   - Limit the executive list to unique actionable hotspots with exact anchors.

7. **Artifact identity and presentation**
   - Ensure terminal filename labels are idempotent.
   - Prevent duplicate `FINAL`, `PENDING-APPROVAL`, or equivalent suffixes.
   - Preserve internal-review and client-delivery controls.

## Acceptance criteria

Phase 6 remains draft until a new exact-SHA Comprehensive package proves all of the following:

- Every required scanner state matches retained evidence from the assessed commit.
- No duplicate stable finding IDs appear in the executive or detailed registers unless explicitly represented as a grouped multi-location finding.
- No duplicate roadmap or backlog mapping appears within a finding.
- The top-priority list contains three unique decision statements.
- Every format agrees on canonical path and line for every exported finding.
- Current required-check health agrees with the exact-SHA workflow matrix.
- Complexity counts distinguish actionable function/component hotspots from structural regions.
- Generated filenames contain each terminal status token at most once.
- English and Spanish packages preserve equivalent facts, scores, limitations, and delivery posture.
- Full CI, security, scanner, frontend, mobile, restart, resilience, and release-proof workflows pass on the final Phase 6 SHA.

## Merge policy

Green CI is necessary but not sufficient. Merge only after a newly generated Comprehensive PDF, Markdown, HTML, JSON, and CSV package visibly demonstrates the corrected scanner states, unique findings, canonical locations, accurate CI state, actionable complexity metrics, and idempotent artifact naming.