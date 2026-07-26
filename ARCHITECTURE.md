# NICO Architecture

This document defines the canonical high-level architecture for the current NICO repository. Historical design notes and compatibility modules do not override these contracts.

## Mission and product boundary

NICO is an authorized, defensive, repair-first technical-assessment platform. Its single customer-facing product is the **NICO Comprehensive Technical Assessment**.

Engagements may differ in repository count, system complexity, infrastructure breadth, integrations, stakeholder evidence, compliance exposure, and human-review effort. Those differences affect scope and price, not the required quality standard.

NICO does not authorize exploitation, credential theft, phishing, malware, persistence, evasion, destructive actions, authentication bypass, or scanning without explicit permission. Production-impacting changes remain human decisions.

## Canonical data flow

```text
Authorized client engagement
  -> validated scope and access
  -> exact run and immutable repository baseline
  -> repository, delivery, infrastructure, and human evidence
  -> isolated defensive analyzer execution
  -> canonical evidence ledger and completeness state
  -> normalized findings and correlation
  -> technical maturity, confidence, assurance, and business impact
  -> remediation and verification planning
  -> canonical assessment package
  -> independent adversarial quality review
  -> human exception review
  -> separately identified approved edition
  -> controlled client delivery and receipt evidence
  -> remediation backlog, verification, baseline, and repair memory
  -> continuing-assurance delta analysis
```

A later stage must not claim completion when its required upstream evidence is pending, unavailable, failed, timed out, malformed, mismatched, unsupported, or unverified.

## Major components

### `nico/`

The Python package contains authorization, assessment orchestration, repository collection, analyzer execution, evidence handling, persistence, scoring, correlation, remediation planning, reporting, quality gates, review, delivery, governance, readiness, recovery, and operational APIs.

Key responsibilities include:

- authorization and scope enforcement;
- repository-target normalization;
- immutable commit and tree capture;
- analyzer execution and safe failure handling;
- secret redaction and bounded output retention;
- evidence provenance and completeness;
- finding normalization, correlation, and contradiction detection;
- technical maturity, assurance, confidence, risk, and business-impact analysis;
- repair prioritization and implementation guidance;
- baseline and drift tracking;
- verification and repair memory;
- canonical artifact generation and cross-format truth gates;
- human exception review and approved-edition workflows;
- controlled delivery;
- production readiness and operational evidence.

### FastAPI application

The production API registers assessment, analyzer, evidence, report, review, delivery, readiness, recovery, and operations routes.

API responses must distinguish among:

- queued;
- running;
- complete;
- partial;
- unavailable;
- failed;
- timed out;
- blocked;
- recovery required;
- expert review required;
- approved;
- delivery authorized;
- revoked.

Compatibility endpoints may remain temporarily, but they must map into the same Comprehensive run, evidence ledger, score model, report package, and approval boundary.

### `apps/web/`

The Next.js application is the primary hosted client and operator interface. The normal customer start path is `/assessment`.

Advanced internal surfaces remain separate when they require elevated identity, review decisions, delivery administration, recovery, diagnostics, operational credentials, or Company Queue permissions. They are not alternative products or competing assessment-start paths.

### Persistence

NICO uses a storage facade with local SQLite support and production Postgres where configured.

Records may include:

- tenants and users;
- clients and engagements;
- scopes and authorization;
- immutable repository baselines;
- runs and stages;
- tool manifests and raw artifacts;
- normalized evidence;
- findings and relationships;
- scores and business-impact assumptions;
- remediation plans and verification;
- reports and presentations;
- quality-review decisions;
- approvals and approved editions;
- delivery grants, receipts, and acknowledgments;
- baselines and deltas;
- repairs and pull-request evidence;
- operational events, metrics, and audit history.

Production responses must disclose durability. In-memory, ephemeral, failed, or unverified writes must not be represented as restart-safe.

## Product and scope contract

The only public product identity is **NICO Comprehensive Technical Assessment**.

Internal complexity classifications are:

- small;
- standard;
- complex;
- enterprise.

These classifications affect workload estimates, concurrency, evidence breadth, human-review routing, and commercial scoping. They must not alter the required truth, evidence, report, review, or delivery controls.

Stored or routed compatibility aliases may exist during migration. They must not:

- expose a second customer product;
- create a second scorecard for the same repository snapshot;
- create a second evidence interpretation;
- generate a lower-quality report;
- bypass a required stage;
- authorize delivery independently.

## Immutable evidence contract

Every assessment must preserve, where applicable:

- tenant, client, project, engagement, and run identity;
- repository identity;
- commit SHA and tree SHA;
- branch or requested ref;
- collection timestamp;
- tool name, version, configuration, and invocation;
- exit status, runtime, timeout, and retries;
- raw artifact location and checksum;
- normalized schema version;
- evidence coverage and completeness;
- failure or limitation reason;
- human modifications and approval history.

Every material finding must retain traceable evidence references. Missing or failed required evidence blocks dependent completion claims.

## Analyzer execution contract

The analyzer worker:

- accepts only authorized targets;
- isolates repository processing in a temporary workspace;
- avoids shell interpolation for untrusted values;
- applies repository-size, time, memory, and output limits;
- checks binary and manifest availability;
- records versions and configuration;
- redacts recognized sensitive patterns from retained operator output;
- retains bounded raw artifacts through approved storage;
- deletes temporary workspaces after completion;
- records requested, executed, unavailable, failed, partial, malformed, and timed-out tools separately;
- uses idempotency keys to prevent duplicate jobs and findings.

A requested tool must execute or appear explicitly with its non-success state. It must not disappear silently.

## Canonical finding contract

A normalized finding should support:

- stable identifier;
- assessment and repository identity;
- immutable commit;
- category and title;
- description;
- severity;
- confidence;
- evidence strength;
- technical and business impact;
- likelihood or exploitability;
- affected assets and code locations;
- supporting evidence and tool sources;
- duplicate, parent, child, and related-finding relationships;
- recommended action and implementation guidance;
- dependencies, owner, effort, and cost assumptions;
- acceptance criteria and verification procedure;
- residual risk;
- workflow and human-review status;
- timestamps and audit history.

Severity, confidence, evidence assurance, technical maturity, and business consequence remain separate concepts.

## Scoring and truth

Scores are evidence signals, not certifications. Missing evidence does not equal passing evidence. Pending or unavailable analyzer records receive no completion credit.

All client artifacts must derive from one canonical assessment model and preserve:

- exact engagement, run, repository, and commit identity;
- evidence provenance;
- coverage and unavailable-data notes;
- technical maturity and evidence-adjusted readiness as separate dimensions;
- finding counts and stable identifiers;
- assumptions and confidence limitations;
- required human review;
- finality and approval state;
- client-delivery authorization state;
- artifact hashes where applicable.

Known cross-format inconsistency blocks review or delivery.

## Independent quality review

Before human review, a logically separate stage challenges:

- unsupported claims;
- weak or contradictory evidence;
- severity drift;
- duplicate findings;
- generic recommendations;
- missing acceptance criteria;
- unrealistic cost or schedule assumptions;
- missing limitations;
- inconsistent scores, counts, identities, or finality;
- improperly sequenced roadmap work;
- client-specific statements unsupported by client evidence.

Quality-review changes and reasons must be auditable.

## Human review and delivery

Automation stops at a human-review gate. Approval creates a separately identified approved edition rather than silently mutating the reviewed package.

Client delivery requires:

- the exact approved edition;
- passing invariant checks;
- verified delivery authorization;
- controlled access;
- receipt or acknowledgment evidence where configured.

Admin credentials, raw delivery tokens, source code, and sensitive evidence must not appear in URLs, browser storage, logs, reports, or build output.

## Controlled remediation

NICO may prepare eligible low-to-moderate-risk remediation specifications, code changes, tests, draft pull requests, reviewer packets, and verification evidence.

Authentication, authorization, cryptography, secrets, tenant isolation, destructive migrations, production infrastructure, billing, compliance controls, production client systems, material data deletion, and unclear rollback require explicit human approval before merge or deployment.

## Continuing assurance

An approved assessment may establish a versioned baseline for targeted delta analysis across commits, dependencies, vulnerabilities, secrets, CI, tests, architecture, infrastructure, permissions, scores, remediation status, and closed-finding verification.

Material changes are escalated. Routine unchanged evidence should not require a complete expensive reassessment unless configured thresholds are exceeded.

## Operations and release integrity

Operational readiness is stricter than HTTP reachability. Production readiness may require:

- frontend and backend deployment identity;
- expected commit alignment;
- durable storage;
- required routes;
- analyzer execution capability;
- queue and recovery health;
- truth guards;
- runtime configuration;
- event and alert persistence;
- backup and recovery evidence;
- successful exact-release acceptance.

Unloaded operational data is neutral. It becomes a failure only after an authenticated load returns failed or unavailable evidence.

## Stable, internal, and compatibility surfaces

The current customer assessment start is `/assessment`.

Internal surfaces include expert review, delivery administration, Company Queue, recovery, diagnostics, readiness, and operating metrics.

Compatibility routes may remain temporarily for migration or recovery, but they must redirect or map into the canonical workflow and must not create competing run identities.

See `MASTER_PLAN.md`, `STATUS.md`, `METRICS.md`, `docs/PROJECT_STATUS.md`, and `docs/OPERATOR_GUIDE.md` for current implementation and operating boundaries.
