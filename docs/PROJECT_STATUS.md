# NICO Project Status

This file is the canonical maturity map for the repository. A feature is not production-proven merely because code or unit tests exist.

The only customer-facing assessment product is the **NICO Comprehensive Technical Assessment**.

## Status definitions

- **Stable** — canonical path, regression-covered, and expected to remain compatible.
- **Operational** — implemented and used, but continuing production proof or usability work remains.
- **Experimental** — implementation evidence exists, but contracts, coverage, security, or operating proof remain incomplete.
- **Compatibility** — retained for migration, recovery, stored-data mapping, or operator-only access; not a separate product.
- **Planned** — accepted work that is not complete.

## Current maturity map

| Area | Status | Current boundary |
|---|---|---|
| Defensive authorization and prohibited-action policy | Stable | Explicit permission remains mandatory. Protected production-impacting changes require human approval. |
| Local-first scanning and local persistence | Stable | Authorized local paths remain the lowest-dependency operating mode. |
| NICO Comprehensive assessment orchestration | Operational | The canonical customer path captures an immutable repository snapshot, runs the configured evidence pipeline, prepares artifacts, verifies cross-format truth, and stops at expert review. Exact-release production proof remains required after relevant changes. |
| Analyzer worker | Operational | Supported tools execute through controlled subprocesses or return explicit unavailable, failed, partial, malformed, or timed-out states. Production reliability and benchmark breadth must continue improving. |
| Evidence provenance and immutable run identity | Operational | Repository, commit, run, scanner, report, approval, and artifact identities exist. Canonical normalization and completeness rules remain a transformation workstream. |
| Technical scoring and assurance | Operational | Technical maturity, evidence assurance, and evidence-adjusted readiness are separated in the current Comprehensive package. Broader benchmark calibration remains incomplete. |
| Finding correlation and remediation planning | Operational | Repair candidates, prioritization, acceptance criteria, verification, and rollback guidance exist in parts. Complete normalized finding coverage and measured preparation automation remain unproven. |
| Decision-grade report generation | Operational | Canonical Markdown, HTML, JSON, and PDF generation and cross-format verification exist. Executive-presentation generation and complete canonical-package consolidation remain to prove. |
| Independent quality review | Experimental | Cross-format and truth gates exist, but a complete logically independent adversarial review across all material claims and recommendations is not yet production-proven. |
| Human review and approved editions | Operational | Required review, approval decisions, separately identified approved artifacts, and delivery blocking exist. Real-client operating evidence must continue. |
| Controlled delivery, receipts, and acknowledgments | Operational | Integrity-bound delivery controls exist. Production operating drills and customer usability evidence remain recurring requirements. |
| Operations readiness, events, and alerts | Operational | Exact deployment identity, persistence readiness, and bounded operational evidence exist. Company Queue and complete exception-based operations are not yet implemented. |
| Guided client intake and scope validation | Experimental | Authorization, repository, client, project, and strategic evidence intake exist. Access validation, scope completeness, evidence requests, and engagement complexity require consolidation. |
| Company Queue | Planned | One internal workspace for engagement state, blockers, reviewers, report readiness, remediation, continuing assurance, commercial milestones, and next actions is not production-proven. |
| Controlled code remediation | Planned | NICO prepares repair candidates and verification guidance. Branch, patch, test, draft-pull-request, reviewer-packet, and post-merge verification automation are not production-proven. |
| Continuing assurance | Experimental | Baseline, drift, repair memory, and monitoring components exist in parts. A commercial material-delta workflow and escalation policy are not production-proven. |
| Hosted multi-tenancy | Experimental | Tenant and scope controls exist in parts. Complete commercial tenant isolation, role, retention, deletion, and cross-tenant proof are not claimed. |
| Production backup, restore, and rollback | Planned | Repository restart and resilience tests exist. Railway Postgres backup, isolated restore, rollback, and measured recovery time remain to prove. |
| Benchmark and maturity measurement | Experimental | Synthetic golden fixtures and reproducibility checks exist. The complete corpus, automatic denominators, and three consecutive target-level runs remain incomplete. |
| Compatibility routes and storage values | Compatibility | Historical values may remain temporarily for migration and recovery. They must map into the same Comprehensive run, evidence ledger, score model, report package, and approval boundary. |
| CLI and local service architecture | Stable | Canonical configuration, scanning, governance, persistence, scoring, repair planning, drift, reporting, verification, and memory run through extracted modules. The compatibility facade must not duplicate implementations. |

## Current release truth

A release is deployable only when required repository CI, security analysis, frontend build, and configured frontend/backend deployment checks pass for the intended commit.

Deployment success does not prove assessment correctness. Release-sensitive changes require exact deployment identity and retained production acceptance evidence, including two consecutive distinct Comprehensive run IDs, the expected immutable repository baseline, completed required stages, generated artifacts, passing cross-format verification, expert review required, and client delivery blocked before approval.

The baseline used by the current transformation branch is `272f5ddde1e81e9f845eab0393f04a356b01d16f`.

## Claims NICO does not make

NICO does not claim:

- guaranteed vulnerability discovery;
- certification or compliance attestation;
- that unavailable analyzers passed;
- that a score proves security;
- that generated repairs are safe without exact-context review and tests;
- that an unapproved report is client-ready;
- that synthetic fixtures are live production evidence;
- that feature existence proves a maturity target;
- that Reparodynamics is independently validated academic science.

## Transformation roadmap

### 0. Truth, governance, and measurement — in progress

- [x] Establish one customer-facing product decision.
- [x] Add repository-level transformation plan, status, decisions, metrics, and runbook documents on the transformation branch.
- [x] Add a machine-readable product and maturity-target contract on the transformation branch.
- [ ] Merge and verify the single-product baseline.
- [ ] Establish the complete versioned benchmark corpus and automatic metric output.

### 1. Production stability — in progress

- [x] Select Railway Postgres as the production persistence contract.
- [x] Add exact frontend and backend deployment identity checks.
- [x] Add production readiness and durable-storage gates.
- [x] Add cross-format finality and expert-review boundaries.
- [ ] Maintain two consecutive live Comprehensive passes for every release-sensitive change.
- [ ] Prove production backup, isolated restore, rollback, and recovery time.
- [ ] Complete a first authorized external GitHub production pilot.

### 2. Single-product consolidation — in progress

- [x] Present one customer-facing assessment workspace.
- [ ] Replace remaining public and internal product-tier terminology.
- [ ] Consolidate API, persistence, report, analytics, and acceptance metadata around one customer-facing identity.
- [ ] Bound all compatibility aliases and prove they cannot create competing scorecards or reports.

### 3. Canonical evidence platform — in progress

- [x] Preserve immutable repository and run identities in core workflows.
- [x] Record explicit analyzer non-success states.
- [ ] Complete one normalized evidence schema for tool manifests, raw artifacts, parsed evidence, completeness, checksums, retries, and audit history.
- [ ] Make required-versus-optional evidence policy explicit and machine-tested.
- [ ] Prove idempotent reruns and duplicate protection across all stages.

### 4. Comprehensive analysis and remediation intelligence — in progress

- [x] Produce technical, security, architecture, delivery, quality, maturity, roadmap, staffing, and business-context analysis in the current workflow.
- [ ] Complete the canonical finding model.
- [ ] Complete duplicate, root-cause, contradiction, and cross-category correlation.
- [ ] Generate implementation-ready remediation plans for at least 95% of material benchmark findings.

### 5. Decision-grade delivery — in progress

- [x] Generate evidence-bound Markdown, HTML, JSON, and PDF artifacts.
- [x] Block review when known cross-format truth checks fail.
- [ ] Generate executive brief, engineering backlog, and executive presentation from the same canonical model.
- [ ] Complete independent adversarial review with auditable changes.
- [ ] Prove 100% material-claim evidence classification.

### 6. Lean company operations — planned

- [ ] Complete guided intake, access validation, scope completeness, evidence requests, and workload classification.
- [ ] Build Company Queue.
- [ ] Route only ambiguous, high-impact, low-confidence, conflicting, protected, or incomplete items to human reviewers.
- [ ] Automatically calculate and prepare the next safe action.

### 7. Controlled remediation — planned

- [ ] Generate remediation specifications and regression-risk classification.
- [ ] Create branches, code changes, tests, and draft pull requests for eligible findings.
- [ ] Generate reviewer packets and post-merge verification evidence.
- [ ] Enforce protected-change human approval.

### 8. Continuing assurance — planned

- [ ] Establish approved versioned baselines.
- [ ] Detect material repository, dependency, vulnerability, secret, CI, test, architecture, infrastructure, permission, score, and verification changes.
- [ ] Produce targeted delta reports and reopen invalidated closures.
- [ ] Escalate only material changes or defensibility failures.

### 9. Security, recovery, and scale — in progress

- [ ] Complete tenant isolation and role-based authorization proof.
- [ ] Complete retention and deletion workflows.
- [ ] Complete production backup/restore/rollback evidence.
- [ ] Test large repositories, large artifacts, concurrent assessments, slow tools, failures, timeouts, and resumable recovery.

### 10. Maturity proof — planned

- [ ] Run the versioned benchmark from clean environments.
- [ ] Produce metrics automatically.
- [ ] Meet each target on three consecutive complete runs.
- [ ] Resolve all Critical and High benchmark regressions.
- [ ] Verify human-time targets on representative engagements.

## Next execution order

1. Merge and verify the single-product transformation baseline.
2. Consolidate runtime product identity and bounded compatibility mappings.
3. Complete canonical evidence and finding schemas.
4. Implement Company Queue and exception-based human review.
5. Complete canonical delivery package and adversarial quality review.
6. Implement controlled remediation and continuing assurance.
7. Complete production recovery, tenancy, scale, external-pilot, and repeated benchmark proof.

This document is authoritative for maturity state. `MASTER_PLAN.md` defines the dependency order, `STATUS.md` records verified progress, and `METRICS.md` defines how target claims are measured.
