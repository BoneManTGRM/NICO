# NICO Completion Program Status

## Authoritative state

The machine-readable source of truth for the active package is:

`docs/client-ready-report-accuracy-observation.json`

Earlier exact production observations remain available in the `docs/production-*observation.json` files and immutable workflow artifacts.

The previously completed dependency remains recorded in:

`docs/exact-head-comprehensive-finality-observation.json`

## Completed dependency

Workstream 1, `exact_head_comprehensive_finality_repair`, remains completed and post-merge verified. Its exact-commit, evidence-retention, human-review, report-preservation, security, and blocked-delivery boundaries remain mandatory.

## First incomplete package

Workstream 2, `exact_head_client_report_accuracy`, remains the first incomplete dependency-ordered package.

Current production main: `9db8f1e7dad4324e86240ff2104a953a559d1a6f`

Current continuation: PR #996, branch `codex/single-render-final-report-v1`.

No later work package may begin before this package is post-merge verified.

## Exact post-merge production failures

PR #992 passed every exact-head check with zero unresolved review threads and merged as `9db8f1e7dad4324e86240ff2104a953a559d1a6f`. Exact Vercel and Railway production identity were verified.

Mobile Restart created exact run `comprun_7474de8e01814ed592659eee68b6a715`. It completed 19 stages, reached `final_comprehensive_report_generation` at 82.61 percent, and terminated with:

`final_report_execution_timeout`

The retained error states that final report generation exceeded the 240-second bounded publication window. No final artifact was retained, human review was not reached, and client delivery remained blocked.

Two-Service Production Acceptance independently created run `comprun_b60488fd729b41bea5263aa1e18ce881` and also terminated as blocked at the final report stage.

## Verified duplicate publication architecture

The current provider still performs two complete artifact passes:

1. the native delegate builds Markdown, HTML, JSON, and a draft PDF;
2. the production execution wrapper parses and semantically finalizes that PDF;
3. `v2_production_authority` then copies the result and calls `finalize_report_package`, rebuilding the authoritative Markdown, HTML, JSON, and PDF.

The exact runtime proof establishes that the combined provider path exceeds the atomic boundary. The source establishes the duplicate render. PR #996 removes the duplicate instead of increasing the timeout.

## Active continuation

PR #996:

- builds a canonical-only source from the same native identity, assessment, stage-summary, decision-summary, and canonical-hash functions;
- skips legacy Markdown, HTML, and PDF rendering for real Comprehensive stage contexts;
- invokes the authoritative v2 renderer exactly once after scanner, score, language, lifecycle, and approval truth are bound;
- uses copy-on-write runtime-truth injection instead of deep-copying the report package;
- retains phase timing for canonical construction, runtime-truth injection, authoritative rendering, and total publication;
- preserves a delegate fallback only for synthetic callers without canonical stage context;
- requires explicit run, repository, commit, and evidence-ledger identity in the final canonical JSON;
- requires a retained canonical truth hash;
- keeps strict semantic and cross-format validation;
- changes no score, scanner result, finding, report design, renderer, section order, or PDF composition;
- keeps human review mandatory and client delivery blocked.

## Completion gate

This package cannot be marked complete until:

- every PR #996 exact-head CI, CodeQL, security, frontend, Postgres, resilience, report, Mobile Restart, iOS WebKit, and production-acceptance check passes;
- zero unresolved review threads remain;
- the exact merge commit is deployed to Vercel and Railway;
- post-merge Mobile Restart, iOS WebKit, and Two-Service Production Acceptance pass;
- two distinct fresh Comprehensive runs reach expert review without manual stage recovery;
- final report generation completes inside the atomic boundary with one authoritative render;
- their existing-design PDFs contain one canonical analyzer-coverage value;
- no completed analyzer is listed as incomplete;
- no stale blocked or running contract is presented as current truth;
- all approval and client-delivery boundaries remain visible.
