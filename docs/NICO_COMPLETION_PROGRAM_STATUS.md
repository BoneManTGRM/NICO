# NICO Completion Program Status

## Authoritative state

The machine-readable source of truth for the active package is:

`docs/client-ready-report-accuracy-observation.json`

The current exact production failure evidence is:

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

Current production main: `c00a715627ff59bc0a35f6e1a3134b854a69b80e`

Current continuation: PR #988, branch `codex/pre-render-authoritative-scanner-truth`.

No later work package may begin before this package is post-merge verified.

## Exact retained production failure

The post-merge Mobile Restart proof created exact run `comprun_94b29a7df4514b6aa45bf92d061f4d5e` against deployed main `c00a715627ff59bc0a35f6e1a3134b854a69b80e`.

The run reached `final_comprehensive_report_generation` at 82.61 percent. The final artifacts existed and were retained:

- Markdown available;
- PDF available;
- 20 PDF pages;
- canonical truth hash retained;
- client delivery still blocked;
- human review not reached.

The semantic publication gate stopped the run with:

`v2_production_publication_failed:ValueError:client report listed completed analyzers as incomplete`

A separately started user run, `comprun_8438671f276445ed87b81c7d25056652`, repeated the 83 percent final-report behavior after the earlier heartbeat-ordering repair.

## Verified root cause

The prior heartbeat race was real and was remediated, but it was not the complete cause of the 83 percent behavior.

The exact report failure is caused by ordering inside the report pipeline:

1. Raw stage evidence can retain recursively copied fields such as `incomplete_analyzers`.
2. `comprehensive_report_package` flattens that stage evidence into client-visible strings before the final canonical scanner reconciliation pass.
3. Later reconciliation corrects canonical JSON but cannot correct strings already rendered into Markdown, HTML, and PDF.
4. The final validator sees an indexed `incomplete_analyzers[n]` path while authoritative exact-run truth says the applicable scanners completed and the incomplete count is zero.
5. The validator correctly blocks publication rather than delivering a contradictory report.

This is a report-truth sequencing defect, not a reason to weaken the semantic gate.

## Active continuation

PR #988:

- derives one pre-render scanner population from direct exact-commit records, the live scanner manifest, and the authoritative client-readiness contract;
- gives current explicit failures precedence over completion;
- gives current exact completion precedence over stale copied incomplete aliases;
- removes only false incomplete-analyzer and incomplete-scanner aliases before stage evidence is flattened;
- preserves genuine failed, unavailable, timed-out, missing, and review-required scanner states;
- synchronizes analyzer counts and coverage before Markdown, HTML, JSON, and PDF are built;
- retains an auditable `pre_render_scanner_truth` manifest, including the exact requested, completed, incomplete, and removed-path populations;
- leaves the final semantic validator strict;
- changes no scanner result, score, finding, report layout, renderer, section order, or PDF composition;
- keeps human review mandatory and client delivery blocked.

## Completion gate

This package cannot be marked complete until:

- every PR #988 exact-head check passes;
- zero unresolved review threads remain;
- the exact merge commit is deployed to Vercel and Railway;
- Mobile Restart, iOS WebKit, and Two-Service Production Acceptance pass post-merge;
- two distinct live Comprehensive runs reach expert review without manual stage recovery;
- their existing-design PDFs contain one canonical analyzer-coverage value;
- no completed analyzer is listed as incomplete;
- no stale blocked contract is presented as current truth;
- all required approval and client-delivery boundaries remain visible.
