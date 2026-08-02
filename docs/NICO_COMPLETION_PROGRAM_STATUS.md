# NICO Completion Program Status

## Authoritative state

The machine-readable source of truth for the active package is:

`docs/client-ready-report-accuracy-observation.json`

The exact current production failure evidence is:

`docs/production-final-report-timeout-orphan-9db8.json`

Earlier retained observations remain available in:

- `docs/production-final-report-background-timeout-f457.json`
- `docs/production-final-report-scanner-truth-failure.json`
- `docs/production-dependency-stage-timeout-observation.json`
- `docs/production-final-report-stage-stall-observation.json`

The previously completed dependency remains recorded in:

`docs/exact-head-comprehensive-finality-observation.json`

## Completed dependency

Workstream 1, `exact_head_comprehensive_finality_repair`, remains completed and post-merge verified. Its exact-commit, evidence-retention, human-review, report-preservation, and blocked-delivery boundaries remain mandatory.

## First incomplete package

Workstream 2, `exact_head_client_report_accuracy`, remains the first incomplete dependency-ordered package.

Current production main: `9db8f1e7dad4324e86240ff2104a953a559d1a6f`

Current continuation: PR #995, branch `codex/durable-final-report-worker`.

No later work package may begin before this package is post-merge verified.

## Exact post-merge production failure

PR #992 merged as `9db8f1e7dad4324e86240ff2104a953a559d1a6f`. Exact Vercel and Railway production identity were verified.

The mandatory post-merge Mobile Restart proof created run `comprun_7474de8e01814ed592659eee68b6a715` against that exact release.

The run reached `final_comprehensive_report_generation` at 82.61 percent and failed with:

`final_report_execution_timeout:stage=final_comprehensive_report_generation`

The retained state proves:

- the final provider exceeded the 240-second atomic request boundary;
- no final report package was retained;
- no report ID or PDF was available;
- human review was not reached;
- client delivery remained blocked;
- the earlier scanner-truth contradiction did not recur.

The bounded final-report helper ran the provider in a daemon thread. Python cannot terminate that thread. After the request timed out and the canonical run became blocked, the render thread could continue consuming the production process.

A separate exact diagnostic captured HTTP 502 responses from both the status and runtime endpoints while concurrent timed-out final-report renders remained active. That evidence is retained in workflow artifact `8838669620`.

## Verified current root cause

The current defect is not missing scanner truth and is not merely an insufficient timeout value.

The final report provider was still coupled to the HTTP request lifetime through an unkillable daemon thread:

1. the request started final rendering;
2. the request waited up to 240 seconds;
3. the run was marked blocked when the wait expired;
4. the provider thread could not be terminated;
5. the orphan render could outlive the request and terminal run state;
6. concurrent orphan renders could degrade production API availability.

Increasing the request timeout would preserve the same failure mode. A durable worker boundary is required.

## Active continuation

PR #995 implements a durable leased final-report worker:

- stores final-report lease owner, expiration, heartbeat, attempt, terminal state, and errors on the same Postgres or SQLite adapter as the canonical run store;
- allows only one active worker for an exact run identity;
- returns the continue request after a short grace interval instead of waiting for PDF rendering;
- keeps status reads available while the report renders;
- heartbeats the lease while the provider runs;
- allows a new process to reclaim an expired lease after process replacement;
- prevents duplicate provider execution while a foreign lease is active;
- allows the provider to finish without an artificial request-lifetime timeout;
- validates report ID, Markdown, HTML, canonical JSON, PDF signature, artifact hashes, and exact run, repository, commit, and evidence-ledger identity;
- writes the complete validated result directly to the canonical Comprehensive run record through its optimistic revision boundary;
- keeps the canonical run record as the only report source of truth;
- retains the bounded copy-on-write scanner-truth and recursive-flatten repairs from PR #992;
- keeps scanner, triage, and executive-analysis background execution unchanged;
- preserves scores, findings, renderer, visual design, section order, detailed report content, and PDF composition;
- preserves strict semantic and cross-format verification;
- keeps human review mandatory and client delivery blocked.

## Completion gate

This package cannot be marked complete until:

- every PR #995 exact-head CI, security, frontend, Mobile Restart, iOS WebKit, Postgres, resilience, report, delivery, and production-acceptance check passes;
- zero unresolved review threads remain;
- exact-head tests prove exclusive leases, persistent heartbeat, duplicate-worker prevention, stale-lease recovery, responsive status reads, and canonical report persistence;
- the exact merge commit is deployed to Vercel and Railway;
- post-merge Mobile Restart, iOS WebKit, and Two-Service Production Acceptance pass;
- two distinct live Comprehensive runs reach expert review without manual stage recovery;
- production status and runtime endpoints remain responsive during final rendering;
- the durable worker heartbeat remains current while the report is running;
- their existing-design PDFs contain one canonical analyzer-coverage value;
- no completed analyzer is listed as incomplete;
- no stale blocked or running contract is presented as current truth;
- all approval and client-delivery boundaries remain visible.
