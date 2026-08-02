# NICO Completion Program Status

## Authoritative state

The machine-readable source of truth for the active package is:

`docs/client-ready-report-accuracy-observation.json`

The exact production failure evidence remains:

`docs/production-final-report-scanner-truth-failure.json`

Earlier retained observations remain available in:

- `docs/production-dependency-stage-timeout-observation.json`
- `docs/production-final-report-stage-stall-observation.json`

The previously completed dependency remains recorded in:

`docs/exact-head-comprehensive-finality-observation.json`

## Completed dependency

Workstream 1, `exact_head_comprehensive_finality_repair`, remains completed and post-merge verified. Its exact-commit, evidence-retention, human-review, report-preservation, and blocked-delivery boundaries remain mandatory.

## First incomplete package

Workstream 2, `exact_head_client_report_accuracy`, remains the first incomplete dependency-ordered package.

Current production main: `a8e42b4874a31a6defc43f05f6d22c5623f379c7`

Current continuation: PR #991, branch `codex/production-final-context-scanner-truth`.

No later work package may begin before this package is post-merge verified.

## Exact post-merge failure after PR #988

PR #988 passed every exact-head CI, security, WebKit, Mobile Restart, Postgres, resilience, report, and production-acceptance check and merged as `a8e42b4874a31a6defc43f05f6d22c5623f379c7`.

The exact merge was deployed to Vercel and Railway. Mandatory post-merge Mobile Restart and iOS WebKit proofs then failed.

Mobile Restart created exact run `comprun_e16515780eb64202a15c0fc3722e2d66` against deployed merge `a8e42b4874a31a6defc43f05f6d22c5623f379c7`.

The run reached `final_comprehensive_report_generation` at 82.61 percent. The final artifacts existed and were retained:

- Markdown available;
- PDF available;
- 20 PDF pages;
- canonical truth hash retained;
- client delivery still blocked;
- human review not reached.

The semantic publication gate stopped the run with the same exact reason:

`v2_production_publication_failed:ValueError:client report listed completed analyzers as incomplete`

## Verified production bypass

The scanner-truth sequencing defect remains verified, but PR #988 bound the repair at a layer production did not reliably use.

The authoritative production path is `nico/comprehensive_final_report_execution_v1.py`:

1. the production application registers and wraps the exact `final_report_generation` provider;
2. `_canonical_final_report_context` copies `prior_stage_results`;
3. it synchronizes score aliases;
4. it invokes the provider directly;
5. the production path can therefore bypass process-global report-builder patches.

This explains why PR #988 passed standalone and integration tests while the exact deployed final-report provider continued to produce the same stale incomplete-analyzer contradiction.

## Active continuation

PR #991 moves the repair into the authoritative production boundary:

- `_canonical_final_report_context` derives exact-run scanner truth before score synchronization;
- only sanitized `prior_stage_results` are passed to the final-report provider;
- direct exact-commit scanner records, the live scanner manifest, and the client-readiness contract are reconciled before the provider can render any format;
- current explicit failures override completion;
- current exact completion overrides stale copied incomplete aliases;
- unidentified evidence remains visible and fail-closed;
- genuine failed, unavailable, timed-out, and missing analyzers remain incomplete;
- the pre-render scanner-truth manifest is retained in the provider context, final result, and evidence envelope;
- the PR #988 report-builder patch remains as defense in depth but is no longer relied on for production correctness;
- the strict final semantic validator remains unchanged;
- no score, scanner result, report design, renderer, section order, or PDF composition changes;
- human review remains mandatory and client delivery remains blocked.

## Completion gate

This package cannot be marked complete until:

- every PR #991 exact-head check passes;
- zero unresolved review threads remain;
- the exact merge commit is deployed to Vercel and Railway;
- Mobile Restart, iOS WebKit, and Two-Service Production Acceptance pass post-merge;
- two distinct live Comprehensive runs reach expert review without manual stage recovery;
- their existing-design PDFs contain one canonical analyzer-coverage value;
- no completed analyzer is listed as incomplete;
- no stale blocked contract is presented as current truth;
- all required approval and client-delivery boundaries remain visible.
