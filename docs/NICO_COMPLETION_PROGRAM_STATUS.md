# NICO Completion Program Status

## Authoritative state

The machine-readable source of truth for the active package is:

`docs/client-ready-report-accuracy-observation.json`

The current production observations are:

- `docs/production-dependency-stage-timeout-observation.json`
- `docs/production-final-report-stage-stall-observation.json`

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
- durable long-stage background execution: `62b53749ca1c3e877187de092fbb5cef4245b0b1`

Current continuation: PR #985, branch `codex/final-report-terminal-state-ordering`.

## Exact retained failure

The retained production assessment advanced past the prior dependency/security failure and reached `Final assessment report` at 83 percent. At 13:30 elapsed, the stage remained active and the report package had not been consumed into the run.

This proves PR #984 improved the earlier 16 percent failure: long-stage work no longer held the browser request open until its bounded timeout. The package remains incomplete because final-report task completion was not reliably visible across request processes.

## Root cause boundary

The live screenshot does not directly expose the background task row or thread ordering. Source inspection identified a concrete race consistent with the observed behavior:

- the provider thread and heartbeat thread persisted the same `client_jobs` task record;
- their writes were not serialized per task;
- a delayed heartbeat could write `running` after a provider wrote `complete`;
- another request process could then continue observing a live task even though the completed report existed locally.

The race is verified in the code path and reproduced by a deterministic regression test. Its production causality is a strong match but is not claimed solely from the screenshot.

## Active continuation

PR #985:

- installs monotonic durable status ordering for Comprehensive background tasks;
- serializes heartbeat and terminal writes per exact task ID;
- prohibits transitions from `complete`, `failed`, or `timed_out` back to `running`;
- recovers an existing durable terminal result before accepting a later heartbeat;
- preserves the full final-report provider result for another request process;
- proves cross-process recovery after clearing all process-local task state;
- keeps the background timeout, orphan recovery, duplicate prevention, exact identity, and one-retry contracts;
- changes no score, scanner finding, report layout, renderer, section order, or PDF composition;
- keeps human review mandatory and client delivery blocked.

## Completion gate

This package cannot be marked complete until:

- every PR #985 exact-head check passes;
- zero unresolved review threads remain;
- the exact merge commit is deployed to Vercel and Railway;
- Mobile Restart, iOS WebKit, and Two-Service Production Acceptance pass post-merge;
- two distinct live Comprehensive runs reach expert review without manual stage recovery;
- their existing-design PDFs contain one canonical analyzer-coverage value, no false incomplete scanner classification, no stale blocked contract presented as current truth, and all required approval and delivery boundaries.

No later work package may begin before this package is post-merge verified.
