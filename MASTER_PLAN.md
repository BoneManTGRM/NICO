# NICO Comprehensive Transformation Master Plan

## Mission

Transform NICO into a production-grade assessment operating system for one flagship product: **NICO Comprehensive Technical Assessment**.

The operating model assumes a founder, two cybersecurity professionals, and NICO. Automation must absorb repeatable collection, analysis, report production, quality control, case progression, remediation preparation, and continuing-assurance work while preserving human authority over security judgment, risk acceptance, legal claims, pricing, production changes, and final delivery.

## Verified baseline

Baseline commit: `272f5ddde1e81e9f845eab0393f04a356b01d16f`.

Verified repository facts at baseline:

- Python/FastAPI backend and Next.js frontend are deployed separately.
- Railway Postgres is the selected production persistence contract.
- The live customer route is `/assessment`, with an English and Spanish experience.
- The current production pipeline captures an immutable repository snapshot, runs the Comprehensive workflow, creates evidence-bound artifacts, performs cross-format truth verification, and stops at expert review.
- Client delivery remains blocked until the exact edition is approved.
- Current release verification includes repository CI, frontend build, deployment identity, production readiness, and two consecutive live Comprehensive passes.
- Public documentation and internal terminology still contain obsolete product-tier language and stale maturity statements.
- Production recovery, external-pilot evidence, continuing assurance, tenant hardening, and autonomous remediation remain incomplete or not yet commercially proven.

## Target architecture

```text
Authorized client engagement
  -> guided intake and scope contract
  -> verified access and immutable repository baseline
  -> versioned tool manifest and evidence ledger
  -> required and optional analyzer execution
  -> normalized evidence and canonical findings
  -> correlation, contradiction detection, and prioritization
  -> business-impact and remediation planning
  -> independent adversarial quality review
  -> human exception queue
  -> canonical client delivery package
  -> approval-bound delivery
  -> remediation backlog and controlled pull requests
  -> continuing-assurance baseline and delta analysis
  -> Company Queue and operating metrics
```

All report formats must derive from one canonical assessment model. Missing, failed, partial, malformed, or unsupported evidence must remain visible and must block claims that require it.

## Dependency-ordered workstreams

### Workstream 0 — Truth, governance, and measurement

- Establish the single-product contract.
- Maintain this master plan, status ledger, decision log, metrics contract, and runbook.
- Replace stale public product terminology.
- Define benchmark fixtures and exact maturity denominators.
- Require changes through focused pull requests and complete CI.

Acceptance:

- Canonical product identity is machine-tested.
- Public documentation is consistent.
- Every maturity claim has an explicit numerator, denominator, benchmark source, and evidence location.

### Workstream 1 — Production stability

- Keep durable Postgres behavior fail-closed.
- Stabilize queues, retries, restarts, scanner timeouts, and resumable execution.
- Preserve exact frontend/backend release identity.
- Require two consecutive live Comprehensive passes on the exact deployed commit.
- Eliminate frontend/backend status divergence.

Acceptance:

- Required workflows are green on the pull request and default branch.
- Production smoke evidence identifies the exact release, runs, repository snapshot, artifacts, and review boundary.
- No required stage is pending, failed, malformed, or silently skipped.

### Workstream 2 — Single-product consolidation

- Make **NICO Comprehensive Technical Assessment** the only public assessment product.
- Retain internal compatibility aliases only where migration requires them.
- Use small, standard, complex, and enterprise solely for internal scope and workload classification.
- Remove competing public workflows, report identities, and scorecards.

Acceptance:

- One public start path, run identity, evidence ledger, scoring model, and delivery package.
- Compatibility aliases cannot create a second client-visible product.

### Workstream 3 — Canonical evidence platform

- Persist immutable repository, commit, tree, run, tool, version, configuration, invocation, runtime, status, checksum, raw artifact, parsed schema, retries, and coverage state.
- Add explicit required/optional tool classification and completeness rules.
- Make reruns idempotent and duplicate-safe.

Acceptance:

- Every material finding is traceable to evidence.
- Required evidence failures block completion.
- Raw and normalized evidence can be audited independently.

### Workstream 4 — Comprehensive analysis and remediation intelligence

- Complete normalized finding fields, correlation, duplicate detection, confidence, evidence strength, business impact, technical impact, ownership, dependencies, acceptance criteria, verification, and residual risk.
- Separate severity, confidence, evidence assurance, and business consequence.
- Generate implementation-ready remediation plans.

Acceptance:

- At least 95% of material benchmark findings enter human review with evidence, severity recommendation, confidence, impact, remediation, acceptance criteria, and verification steps.

### Workstream 5 — Decision-grade delivery

- Generate executive brief, technical report, roadmap, engineering backlog, machine-readable package, and executive presentation from canonical data.
- Add hard cross-format invariants and an independent adversarial review.

Acceptance:

- Failed invariants block delivery.
- Every material factual claim is evidence-backed or explicitly classified as inference, limitation, or client-provided context.
- Report production reaches the documented benchmark target without manual copy-and-paste assembly.

### Workstream 6 — Lean company operations

- Build guided intake, access validation, scope completeness, evidence requests, human exception routing, and Company Queue.
- Calculate and prepare the next safe action for every engagement.

Acceptance:

- Routine case progression is automated while high-impact or ambiguous decisions remain human-controlled.
- The founder and two cybersecurity professionals operate primarily through exceptions and approvals.

### Workstream 7 — Controlled remediation

- Generate remediation specifications, dedicated branches, code changes, tests, draft pull requests, reviewer packets, and verification evidence for eligible findings.
- Enforce risk-based approval gates.

Acceptance:

- No high-risk change is merged or deployed without explicit human authorization.
- Eligible low-to-moderate-risk benchmark repairs achieve the documented automation target with passing tests and rollback instructions.

### Workstream 8 — Continuing assurance

- Establish approved baselines.
- Detect material changes in commits, dependencies, vulnerabilities, secrets, CI, tests, architecture, infrastructure, permissions, scores, and closed findings.
- Generate targeted delta reports and escalate material changes.

Acceptance:

- Routine delta analysis meets the benchmark automation target.
- Closed findings reopen when verification no longer holds.

### Workstream 9 — Security, recovery, and scale

- Complete tenant isolation, role-based access, audit logs, secret management, retention, deletion, backup, restore, rollback, load, concurrency, and recovery tests.

Acceptance:

- Cross-tenant access tests pass.
- Backup, isolated restore, and rollback are proven without exposing secrets.
- Large and concurrent benchmark workloads remain bounded and resumable.

### Workstream 10 — Maturity proof

- Run the documented benchmark suite from clean environments.
- Produce metrics automatically.
- Require three consecutive complete runs at target.
- Resolve all Critical and High benchmark regressions.

Acceptance:

- Targets are reported as measured results rather than feature estimates.
- Human-time targets are verified on representative engagements.

## Merge policy

Autonomous merge may be considered only for low-risk changes after all required checks pass. Authentication, authorization, cryptography, secret handling, tenant isolation, destructive migrations, production infrastructure, billing, legal/compliance claims, production client code, material deletion, and unclear rollback always require explicit human approval.

## Completion rule

Merged features do not establish completion. NICO is mature only when production behavior and three consecutive benchmark runs prove the acceptance criteria, no unresolved Critical defect remains, High defects are resolved or formally accepted, documentation matches runtime behavior, and operational rollback/recovery procedures are executable.
