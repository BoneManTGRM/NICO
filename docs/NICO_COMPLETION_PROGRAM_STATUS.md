# NICO Completion Program Status

## Authoritative state

The machine-readable source of truth for the active package is:

`docs/client-ready-report-accuracy-observation.json`

The current production timeout evidence is:

`docs/production-dependency-stage-timeout-observation.json`

The previously completed dependency remains recorded in:

`docs/exact-head-comprehensive-finality-observation.json`

## Completed dependency

Workstream 1, `exact_head_comprehensive_finality_repair`, remains completed and post-merge verified. Its exact-commit, evidence-retention, human-review, report-preservation, and blocked-delivery boundaries remain mandatory.

## First incomplete package

Workstream 2, `exact_head_client_report_accuracy`, remains the first incomplete dependency-ordered package.

Relevant merged repairs:

- finality and exact-run continuation: `ccc399f4766d455a78adf690a1f7f43c1e7c6e3d`
- durable run recovery: `116a896f031f258426b7f93759323667867c34ee`
- stage watchdog and WebKit transport: `ff239fbba71a917ef164848bbe6b1a86d760d546`
- canonical report coverage synchronization: `010263d0db823e46ff1c47ee21f89bef84af5f86`
- false recovery-overlay removal: `671d213ca70d612e1f0386cb05d86b138da0df81`
- bounded individual stage execution: `62354ea2db1f62f09eeba373e50efedbcb50c598`

Current continuation: PR #984, branch `codex/async-comprehensive-stage-execution`.

## Exact retained failure

Production run `comprun_99d7f2630eb74db5be7725c2fd9fd93c` reached `dependency_security_static_analysis` at 16 percent. At 8:00 elapsed, the browser displayed:

`The current assessment stage exceeded the bounded response time. The exact run was retained and can be retried.`

The recovery contract behaved correctly:

- the request did not wait forever;
- the exact run ID remained visible;
- manual retry and clear controls were available;
- human review remained required;
- client delivery remained blocked.

The assessment still failed its commercial workflow requirement because a normal dependency and security scan required manual recovery instead of progressing automatically.

## Root cause boundary

The screenshot and exact run prove that the long-stage provider did not return inside the continuation response window. They do not identify which internal scanner, storage call, or provider operation consumed that entire window.

The architectural defect is established: known long providers were still invoked synchronously inside `/continue`, even though the scanner worker below the dependency stage already has an asynchronous job model. A browser request must not remain open for the duration of a scanner, executive-analysis, or report-generation provider call.

## Active continuation

PR #984:

- executes dependency/security analysis, deep scanner triage, executive briefing, and final report generation behind a durable background task boundary;
- returns an in-progress stage result promptly while provider work continues;
- binds every task to immutable run, repository, commit, evidence ledger, stage, poll iteration, and recovery attempt;
- stores cross-process task state in the existing `client_jobs` evidence surface;
- retains task heartbeats and bounded orphan recovery;
- prevents a repeated continuation request from launching the same poll twice;
- increments the poll identity only after a provider result is consumed into the canonical stage record;
- allows a recovered stage to use a new task identity without rerunning completed stages;
- writes provider results into the canonical run only from the request thread;
- discards late provider results after a hard timeout;
- preserves the existing direct timeout path for short stages;
- changes no score, scanner finding, report layout, renderer, section order, or PDF composition;
- keeps human review mandatory and client delivery blocked.

## Completion gate

This package cannot be marked complete until:

- every PR #984 exact-head check passes;
- zero unresolved review threads remain;
- the exact merge commit is deployed to Vercel and Railway;
- Mobile Restart, iOS WebKit, and Two-Service Production Acceptance pass post-merge;
- two distinct live Comprehensive runs reach expert review without manual stage recovery;
- their existing-design PDFs contain one canonical analyzer-coverage value, no false incomplete scanner classification, no stale blocked contract presented as current truth, and all required approval and delivery boundaries.

No later work package may begin before this package is post-merge verified.
