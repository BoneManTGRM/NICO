# NICO Completion Program Status

## Authoritative state

The machine-readable source of truth for the active package is:

`docs/client-ready-report-accuracy-observation.json`

The exact current production failure evidence is:

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

Current continuation branch: `codex/final-report-atomic-single-pass`.

No later work package may begin before this package is post-merge verified.

## Exact post-merge production failure

PR #991 merged as `f457ed47fc374358fe47e23128066c771db4f261`. Exact Vercel and Railway production identity were verified.

The mandatory post-merge Mobile Restart proof created run `comprun_33925b5a68994333ab148ec925d5bd2f` against that exact release.

The run completed 19 stages and reached `final_comprehensive_report_generation` at 82.61 percent. It then failed with:

`background_stage_execution_timeout:stage=final_comprehensive_report_generation:task_id=comprehensive_stage_83fcc878a480cb96e397165c6ada:elapsed_seconds=908.093`

The retained state proves:

- the final provider exceeded the generic 900-second detached background boundary;
- no final report package was retained;
- no report ID or PDF was available;
- human review was not reached;
- client delivery remained blocked;
- the prior completed-analyzer semantic contradiction was not the current failure.

## Verified current root cause

Final report publication still depended on the generic background-stage mechanism. That path combines process-local execution with task telemetry and performs repeated large-evidence processing before final rendering.

The production final-report path also performed scanner-truth traversal at the provider boundary and again in the patched report builder. The native report detail flattener had an emitted-line limit but no shared node-visit limit, so deeply nested evidence that emitted few lines could still consume an unbounded amount of work.

## Active continuation

The current branch implements one linked repair:

- dispatch final report generation before the generic background-stage branch;
- execute it through a bounded atomic publication boundary;
- avoid another full evidence-tree deepcopy inside the final worker;
- canonicalize scanner truth through bounded copy-on-write traversal;
- embed a manifest that causes the report builder to skip duplicate canonicalization;
- bound recursive report evidence flattening with one shared visit budget;
- validate report ID, Markdown, HTML, canonical JSON, PDF signature, hashes, and exact run identity;
- persist the complete validated result through the canonical Comprehensive run-store transaction;
- keep scanner, triage, and executive-analysis background execution unchanged;
- keep the final semantic verifier strict;
- preserve scores, findings, report design, renderer, section order, and PDF composition;
- preserve human review and blocked client delivery.

## Completion gate

This package cannot be marked complete until:

- every exact-head CI, security, frontend, Mobile Restart, iOS WebKit, Postgres, resilience, report, and production-acceptance check passes;
- zero unresolved review threads remain;
- the exact merge commit is deployed to Vercel and Railway;
- post-merge Mobile Restart, iOS WebKit, and Two-Service Production Acceptance pass;
- two distinct live Comprehensive runs reach expert review without manual stage recovery;
- their existing-design PDFs contain one canonical analyzer-coverage value;
- no completed analyzer is listed as incomplete;
- final report generation completes inside the bounded atomic publication path;
- no stale blocked or running contract is presented as current truth;
- all approval and client-delivery boundaries remain visible.
