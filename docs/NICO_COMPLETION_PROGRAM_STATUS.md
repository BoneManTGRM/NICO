# NICO Completion Program Status

## Authoritative state

The machine-readable source of truth for the active package is:

`docs/client-ready-report-accuracy-observation.json`

The previously completed dependency remains recorded in:

`docs/exact-head-comprehensive-finality-observation.json`

## Completed dependency

Workstream 1, `exact_head_comprehensive_finality_repair`, remains completed and post-merge verified. Its report-truth, exact-commit, evidence-retention, human-review, and blocked-delivery boundaries remain mandatory.

## First incomplete package

Workstream 2, `exact_head_client_report_accuracy`, is the first incomplete dependency-ordered package.

Release base: `78c8a62393446a9a70a675d905c7a9201a8d21b5`

Continuation pull request: `#974`

The release deployed successfully to Vercel and Railway and passed every PR #972 exact-head workflow with zero unresolved review threads. Post-merge live acceptance then failed on two distinct Comprehensive runs at `final_comprehensive_report_generation`.

The retained exact-run evidence established two coupled defects:

1. The production scanner runtime still executed Bandit through the legacy CSV path, which failed parsing and left 8 of 9 requested analyzers complete.
2. The final report path derived client-facing coverage from stale or filtered projections, producing conflicting 78 and 100 values instead of the exact-run 89 value.

## Active repair

The active repair:

- binds Bandit JSON at both the named delegate and the authoritative problem-tool dispatch imported by snapshot scanner authority;
- preserves the exact-run `tools_requested` manifest as the coverage denominator;
- retains failed, missing, unavailable, or timed-out requested tools as explicit incomplete scanner records;
- ignores recursive stale projection counts;
- reapplies exact-run truth after the existing renderer's authoritative projection;
- preserves the current NICO visual design, section order, detailed content, and PDF composition;
- changes no score merely to satisfy a gate;
- keeps human review mandatory and client delivery blocked.

## Completion gate

This package cannot be marked complete until:

- every exact-head PR check passes;
- zero unresolved review threads remain;
- the exact merge commit is deployed to Vercel and Railway;
- Mobile Restart, iOS WebKit, and Two-Service Production Acceptance pass post-merge;
- two distinct live Comprehensive runs reach expert review;
- their existing-design PDFs contain one canonical analyzer-coverage value, no false incomplete scanner classification, no stale blocked contract presented as current truth, and all required approval and delivery boundaries.

No later work package may begin before this package is post-merge verified.
