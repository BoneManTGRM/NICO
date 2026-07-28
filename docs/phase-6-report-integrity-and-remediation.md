# Phase 6 - Final Report Integrity and Production Remediation

## Baseline

Phase 6 begins from main after Phase 5 merge commit `2056ceed71b517b61bb21c0ba8fda522e1ae8940` and Comprehensive report run `comprun_35f88b49648d438a86a9490c244b8046`.

The baseline report contains customer-facing truth and usability defects:

- Bandit and ESLint appear failed, while Gitleaks and OSV Scanner appear partial, despite retained complete exact-SHA evidence.
- Identical analyzer findings, stable IDs, locations, roadmap mappings, and remediation records repeat across the report.
- Raw analyzer prose is promoted into executive titles.
- The same stable finding can display different source locations across report surfaces.
- Assessed-commit CI health is mixed with default-branch and historical workflow outcomes.
- Complexity output emphasizes raw synthetic-region totals rather than unique actionable functions and components.
- Terminal filename labels can be appended repeatedly.
- The Phase 5 comparison section and Express comparison language expose internal implementation history in a customer report.

## Required work packages

1. **Exact-SHA evidence reconciliation**
   - Select scanner evidence in this precedence order: exact assessed commit, complete retained raw artifact, verified artifact hash, complete valid exit state, newest valid exact-commit record.
   - Prevent stale or lower-authority records from overriding a newer valid record.
   - Treat missing or incomplete evidence as a limitation, never as clean evidence.

2. **Canonical finding identity and deduplication**
   - Build identity from tool, rule ID, repository-relative path, canonical location, symbol or query context, and normalized evidence fingerprint.
   - Group related occurrences without losing their individual locations.
   - Detect stable-ID collisions rather than allowing conflicting locations to reuse one ID.
   - Deduplicate roadmap mappings, backlog mappings, acceptance criteria, and grouped locations while preserving deterministic order.

3. **Security finding disposition**
   - Inspect each reported SQL-construction result against the exact source.
   - Repair unsafe value interpolation or externally controlled identifiers.
   - Retain source-specific, evidence-backed bounded dispositions for fixed structure, parameter binding, closed placeholder sets, or allowlisted identifier composition.
   - Expire every bounded disposition when its source construction changes.

4. **Executive and technical separation**
   - Store concise executive titles separately from technical summaries and full analyzer messages.
   - Use decision language in cover and executive sections.
   - Keep original analyzer prose in technical evidence detail.

5. **Location and cross-format integrity**
   - Normalize repository paths and line numbers once from the exact assessed snapshot.
   - Generate PDF, Markdown, HTML, JSON, CSV, remediation, roadmap, and backlog records from one canonical model.
   - Fail the build when factual projections diverge between formats.

6. **CI and release truth**
   - Report assessed-commit required checks, current default-branch checks, and bounded historical reliability as three independent records.
   - Exclude active and queued runs from historical failure counts.
   - Never allow historical failures to change the assessed-commit status.

7. **Actionable complexity**
   - Classify production functions and components, report generation, tests, generated or vendor code, and synthetic module regions separately.
   - Emphasize unique production and report-generation hotspots above the accepted threshold.
   - Retain raw totals only as auditable supporting data.

8. **Artifact identity and presentation**
   - Normalize recognized terminal suffixes before appending one authoritative state.
   - Make filename processing idempotent.
   - Use concise executive tables and structured finding cards instead of unreadable wide tables.
   - Avoid forced page padding and nearly empty continuation pages.

9. **Customer-facing scope cleanup**
   - Remove the `Verified Change Since Phase 5 Baseline` control, chart row, appendix, and Phase-numbered exports.
   - Remove `Why this is broader than Express` and other tier-comparison wording.
   - Replace internal comparison language with neutral `Assessment Coverage` content.

10. **Language parity**
    - Preserve identical repository and commit identity, scanner states, scores, findings, risk IDs, locations, priorities, criteria, limitations, CI state, and approval posture in English and Mexican Spanish editions.
    - Permit only labels and explanatory prose to differ by language.

## Acceptance criteria

Phase 6 remains draft until a fresh exact-SHA Comprehensive package proves all of the following:

- Every required scanner state matches complete retained evidence from the assessed commit.
- Only genuinely incomplete scanners appear under limitations.
- Executive and detailed registers contain unique canonical findings and stable IDs.
- Every SQL-construction occurrence is repaired or has a source-specific traceable disposition.
- Every format agrees on scores, scanner states, risk IDs, priority, status, canonical location, limitation count, CI state, delivery status, and mappings.
- Assessed-commit required checks are green independently of default-branch and historical metrics.
- Complexity output identifies a defined population and a unique prioritized actionable hotspot list.
- Generated filenames contain one authoritative terminal suffix and remain unchanged when processed again.
- The report contains no Phase 5 customer section and no Express comparison language.
- English and Mexican Spanish packages have identical factual projections.
- The report is substantially less repetitive while retaining the complete evidence ledger in machine-readable artifacts.
- Full CI, security, scanner, frontend, mobile, WebKit, restart, resilience, database, and release-proof workflows pass on the final Phase 6 SHA.
- Two consecutive candidate acceptance passes are retained before merge; post-merge production acceptance remains required.

## Merge policy

Green CI is necessary but not sufficient. Merge only after a newly generated exact-SHA Comprehensive PDF, Markdown, HTML, JSON, and CSV package visibly demonstrates corrected scanner states, unique findings, source-reviewed dispositions, canonical locations, accurate CI truth, actionable complexity, idempotent artifact naming, English-Spanish factual parity, and preserved human approval controls.
