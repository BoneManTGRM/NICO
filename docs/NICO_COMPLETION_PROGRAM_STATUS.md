# NICO Completion Program Status

## Authoritative state

The machine-readable source of truth for the active package is:

`docs/client-ready-report-accuracy-observation.json`

The current production observations are:

- `docs/production-dependency-stage-timeout-observation.json`
- `docs/production-final-report-stage-stall-observation.json`
- `docs/production-fresh-final-report-stall-observation.json`

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
- long-stage background execution: `62b53749ca1c3e877187de092fbb5cef4245b0b1`
- background terminal ordering: `53923aa5db6d96ca5be73f37dee376b49d5fd092`
- permanent active-run reset control: `c00a715627ff59bc0a35f6e1a3134b854a69b80e`

Current continuation: branch `codex/atomic-final-report-publication`.

## Exact fresh-run failure

A new assessment created after the prior repairs produced exact run:

`comprun_8438671f276445ed87b81c7d25056652`

A read-only production diagnostic queried the exact run and runtime endpoints. The retained run was assessing `BoneManTGRM/NICO` at commit `c00a715627ff59bc0a35f6e1a3134b854a69b80e` and showed:

- status `running`;
- current stage `final_comprehensive_report_generation`;
- canonical progress `82.61%`;
- 19 completed stages;
- revision 94;
- current-stage reason `background_stage_execution_in_progress`;
- no `stage_execution` metadata or task ID in the persisted current-stage result;
- no report ID or PDF;
- no recorded blocker;
- human review not reached;
- client delivery still blocked.

Runtime diagnostics confirmed that the application and shared Postgres run store were ready. The full persisted record contained the same generic running final stage. This is not a stale browser-only display.

Diagnostic PR #987 was closed without merge after retaining the read-only artifact.

## Corrected root-cause boundary

The fresh failure disproves the earlier heartbeat-ordering race as the complete cause. That race was real and was repaired, but the publication architecture remained unsafe:

- final report generation still ran in a process-local daemon thread;
- the process-local `_TASKS` map was part of execution authority;
- `client_jobs` stored status/result telemetry but no independent durable worker claimed and executed the job;
- `_put_job` swallowed storage failures and could leave a result available only inside one web process;
- the final report result contains large PDF, HTML, Markdown, and JSON artifacts;
- the fresh canonical stage retained only a generic running skeleton and lost the task identity needed for deterministic recovery.

The evidence verifies the architectural failure. The public diagnostic does not identify whether the exact event was a web-process lifecycle interruption or failure to durably retain the large result in generic job telemetry, so neither event is claimed as individually proven.

## Active continuation

The active repair:

- removes `final_comprehensive_report_generation` from detached background execution at the run-service dispatch boundary;
- generates the final report within the existing bounded request execution boundary;
- requires a complete report ID, Markdown, HTML, JSON, and valid PDF before the stage may complete;
- verifies exact run, repository, commit, and evidence-ledger identity;
- retains artifact hashes and validation evidence;
- writes the complete result to the canonical Comprehensive run store from the request thread;
- returns an explicit fail-closed timeout or artifact-validation failure instead of an indefinite 83-percent running state;
- keeps scanner, triage, and executive-analysis background behavior unchanged;
- preserves all 19 prior completed stages;
- preserves the existing renderer, visual design, section order, detailed content, and PDF composition;
- changes no score and no scanner finding;
- keeps human review mandatory and client delivery blocked.

## Completion gate

This package cannot be marked complete until:

- every continuation PR exact-head check passes;
- zero unresolved review threads remain;
- the exact merge commit is deployed to Vercel and Railway;
- a fresh public assessment passes the final-report stage without manual retry;
- Mobile Restart, iOS WebKit, and Two-Service Production Acceptance pass post-merge;
- two distinct live Comprehensive runs reach expert review without manual stage recovery;
- their existing-design PDFs contain one canonical analyzer-coverage value, no false incomplete scanner classification, no stale blocked contract presented as current truth, and all required approval and delivery boundaries.

No later work package may begin before this package is post-merge verified.
