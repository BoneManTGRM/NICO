# NICO Completion Program Status

## Authoritative state

The machine-readable source of truth for the active package is:

`docs/client-ready-report-accuracy-observation.json`

The current exact production failure evidence is:

`docs/production-final-report-background-timeout-f457.json`

Earlier retained observations remain available in:

- `docs/production-final-report-scanner-truth-failure.json`
- `docs/production-dependency-stage-timeout-observation.json`
- `docs/production-final-report-stage-stall-observation.json`

The previously completed dependency remains recorded in:

`docs/exact-head-comprehensive-finality-observation.json`

## Completed dependency

Workstream 1, `exact_head_comprehensive_finality_repair`, remains completed and post-merge verified. Its exact-commit, evidence-retention, human-review, report-preservation, and blocked-delivery boundaries remain mandatory.

## First incomplete package

Workstream 2, `exact_head_client_report_accuracy`, remains the first incomplete dependency-ordered package.

Current production main: `f457ed47fc374358fe47e23128066c771db4f261`

Current continuation: PR #993, branch `codex/atomic-final-report-publication-v3`.

No later work package may begin before this package is post-merge verified.

## Exact post-merge failure after PR #991

PR #991 passed every exact-head CI, CodeQL, security, WebKit, Mobile Restart, Postgres, resilience, report, and production-acceptance check with zero unresolved review threads. It merged as `f457ed47fc374358fe47e23128066c771db4f261` and deployed successfully to Vercel and Railway.

Its production-bound scanner-truth repair remains required and is preserved.

Mandatory exact-main Mobile Restart, iOS WebKit, and Two-Service Production Acceptance then failed.

Mobile Restart created exact run:

`comprun_33925b5a68994333ab148ec925d5bd2f`

The exact deployed run reached `final_comprehensive_report_generation` at 82.61 percent and then terminated with:

`background_stage_execution_timeout`

Retained details:

- task ID `comprehensive_stage_83fcc878a480cb96e397165c6ada`;
- elapsed background execution 908.093 seconds;
- configured background boundary 900 seconds;
- reason `stage_progress_stalled`;
- no final report artifacts retained;
- human review not reached;
- client delivery remained blocked.

This is no longer a browser-only or scanner-alias failure. The final report itself is still incorrectly executed through generic detached background infrastructure.

## Active continuation

PR #993 is based exactly on current production main and replaces the stale divergent PR #990.

The active repair:

- dispatches `final_comprehensive_report_generation` before the generic background-stage branch;
- executes final report generation through the existing bounded stage boundary;
- requires report ID, Markdown, HTML, canonical JSON, and a valid PDF before completion;
- verifies exact run, repository, commit, and evidence-ledger identity;
- retains artifact hashes and validation evidence;
- returns the complete result to the request thread for the canonical Comprehensive run-store transaction;
- never permits a generic `background_stage_execution_in_progress` result to complete final publication;
- fails closed with an explicit timeout or artifact-validation reason rather than retaining an indefinite 83-percent task;
- preserves background execution for scanner, triage, and executive-analysis stages;
- preserves the PR #991 production-bound scanner-truth reconciliation before report rendering;
- preserves all previously completed stage evidence;
- preserves the existing renderer, visual design, section order, detailed content, and PDF composition;
- changes no score, scanner result, finding, or client-facing design;
- keeps the strict semantic validator unchanged;
- keeps human review mandatory and client delivery blocked.

## Stale pull request disposition

PR #990 was created from the previous main and diverged after PR #991 merged. Its exact head also failed NICO CI because legacy fixtures did not provide valid final report artifacts. It must not be merged or rebased as the authoritative continuation. PR #993 rebuilds the same necessary atomic-publication boundary from current main with corrected compatibility coverage.

## Completion gate

This package cannot be marked complete until:

- every PR #993 exact-head check passes;
- zero unresolved review threads remain;
- the exact merge commit is deployed to Vercel and Railway;
- a fresh public assessment passes the final-report stage without manual retry;
- Mobile Restart, iOS WebKit, and Two-Service Production Acceptance pass post-merge;
- two distinct live Comprehensive runs reach expert review without manual stage recovery;
- their existing-design PDFs contain one canonical analyzer-coverage value;
- no completed analyzer is listed as incomplete;
- no stale blocked contract is presented as current truth;
- all required approval and client-delivery boundaries remain visible.
