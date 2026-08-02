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

Current production main: `494c274bb455a39190b0e00c52fc3aa9f4de892e`

Current continuation: PR #997, branch `codex/retained-scanner-final-publication`.

No later work package may begin before this package is post-merge verified.

## Exact post-merge production failure

PR #996 removed the duplicate legacy artifact render, passed every exact-head check with zero unresolved review threads, and merged as `494c274bb455a39190b0e00c52fc3aa9f4de892e`. Exact Vercel and Railway production identity were verified.

Mobile Restart created exact run `comprun_2b6992f1881449d39a7e231c0a133428`. The interface reached `Blocked during final report generation`; no report actions or artifacts were available, and the exact-run status request also timed out.

Two-Service Production Acceptance independently created exact run `comprun_a9bb37cc43504f5b92aaa743f2f26d9b`. It completed 19 stages, reached `final_comprehensive_report_generation` at 82.61 percent, repeatedly timed out status reads during final publication, and terminated blocked without reaching expert review.

The single-render repair was necessary but did not make the final publication path bounded or responsive.

## Verified remaining synchronous dependency

The final publisher still called `comprehensive_native_providers._scan(context)` inside `_inject_live_runtime_truth` after the dependency/security stage had already completed.

That path:

1. reopens the full scanner result store during final report generation;
2. imports complete scanner records, including findings and retained output payloads;
3. adds those records to canonical JSON;
4. sends the enlarged structure through reconciliation, Markdown, HTML, JSON, CSV, UI, and PDF publication passes.

The source proves this hidden synchronous work remains. Exact production evidence proves final publication still monopolizes the production process long enough for status reads to time out. PR #997 removes the work without claiming it is the only theoretically possible remaining cost.

## Active continuation

PR #997:

- retains one compact exact-SHA record per analyzer during the dependency/security stage;
- preserves scanner name, artifact hash, exact commit match, exit code, verification state, finding count, bounded triage counts, scan ID, and raw-artifact reference;
- leaves raw scanner findings and output previews in the scanner evidence store rather than copying them into the Comprehensive run record;
- publishes final reports only from scanner evidence already retained by the exact run;
- performs no scanner-store read, repository clone, or scanner execution during final report generation;
- preserves `completed_with_findings` through retained finding counts;
- keeps manifest-only evidence partial and fail-closed rather than silently upgrading it;
- retains the single authoritative v2 renderer and atomic run-store publication boundary;
- keeps strict semantic and cross-format validation;
- changes no score, finding disposition, report design, renderer, section order, or PDF composition;
- keeps human review mandatory and client delivery blocked.

A durable final-report worker is not active. It becomes the next dependency only if this bounded retained-evidence payload still cannot complete or keep status endpoints responsive in exact post-merge production evidence.

## Completion gate

This package cannot be marked complete until:

- every PR #997 exact-head CI, CodeQL, security, frontend, Postgres, resilience, report, Mobile Restart, iOS WebKit, and production-acceptance check passes;
- zero unresolved review threads remain;
- the exact merge commit is deployed to Vercel and Railway;
- post-merge Mobile Restart, iOS WebKit, and Two-Service Production Acceptance pass;
- two distinct fresh Comprehensive runs reach expert review without manual stage recovery;
- status endpoints remain responsive during final report publication;
- final report generation completes inside the atomic boundary with one authoritative render and no final-stage scanner-store read;
- their existing-design PDFs contain one canonical analyzer-coverage value;
- no completed analyzer is listed as incomplete;
- no stale blocked or running contract is presented as current truth;
- all approval and client-delivery boundaries remain visible.
