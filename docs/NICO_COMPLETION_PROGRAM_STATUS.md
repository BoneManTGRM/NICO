# NICO Completion Program Status

## Authoritative state

The machine-readable source of truth for the active package is:

`docs/client-ready-report-accuracy-observation.json`

The previously completed dependency remains recorded in:

`docs/exact-head-comprehensive-finality-observation.json`

## Completed dependency

Workstream 1, `exact_head_comprehensive_finality_repair`, remains completed and post-merge verified. Its report-truth, exact-commit, evidence-retention, human-review, and blocked-delivery boundaries remain mandatory.

## First incomplete package

Workstream 2, `exact_head_client_report_accuracy`, remains the first incomplete dependency-ordered package.

Implementation merge: `ccc399f4766d455a78adf690a1f7f43c1e7c6e3d`

Current main: `116a896f031f258426b7f93759323667867c34ee`

Continuation branch: `codex/exact-head-client-report-accuracy-continuation`

PR #974 passed all exact-head checks and retained zero unresolved review threads. The exact current main release is deployed to both Vercel and Railway. The package is not complete because the mandatory post-merge production proofs still fail.

## Retained post-merge failures

The retained exact-run evidence now establishes three release blockers:

1. Mobile Restart created `comprun_0b77c5b34d984eb0bcdbb44328e80c19`, but the run stopped at `final_comprehensive_report_generation` before expert review.
2. iOS WebKit completed no persisted run identity after the single intake click. Chromium could create a run, so the continuation transport must preserve the exact Request body across WebKit as well.
3. Two-Service Production Acceptance created `comprun_b6a647acac04427c8c8ab4324fec05a0`, then called continuation 362 times while `dependency_security_static_analysis` remained at 74 percent active-stage progress and 13.04 percent canonical progress. Revision-only writes were incorrectly treated as continued operation.

The browser-visible final-report block remains truthful. The continuation must expose and retain the bounded technical reason rather than changing wording or bypassing the gate.

## Active continuation

The continuation:

- adds a durable stage-progress watchdog that ignores revision-only, heartbeat-only, and timestamp-only mutations;
- converts a stage with bounded no-progress attempts or elapsed time into a clear terminal `stage_progress_stalled` result;
- preserves scanner evidence and exact-run identity when a stall is declared;
- permits one explicit retry of the stalled stage without rerunning previously completed stages;
- prohibits automatic unlimited stalled-stage retries;
- sends a proxied WebKit Request exactly once rather than constructing a bounded Request and then reapplying the same body/init to `fetch`;
- preserves the current NICO report renderer, visual design, section order, detailed content, and PDF composition;
- changes no score to satisfy a gate;
- keeps human review mandatory and client delivery blocked.

## Completion gate

This package cannot be marked complete until:

- every continuation PR exact-head check passes;
- zero unresolved review threads remain;
- the exact merge commit is deployed to Vercel and Railway;
- Mobile Restart, iOS WebKit, and Two-Service Production Acceptance pass post-merge;
- two distinct live Comprehensive runs reach expert review;
- their existing-design PDFs contain one canonical analyzer-coverage value, no false incomplete scanner classification, no stale blocked contract presented as current truth, and all required approval and delivery boundaries.

No later work package may begin before this package is post-merge verified.
