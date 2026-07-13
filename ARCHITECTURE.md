# NICO Architecture

This document is the canonical high-level architecture for the current NICO repository. Historical design notes and patch documents may explain how individual features evolved, but they do not override the contracts described here.

## Mission and boundary

NICO is an authorized, defensive, repair-first technical assessment platform. It collects evidence, identifies risk and drift, ranks repair candidates, prepares verification steps, preserves repair memory, and produces evidence-bound reports.

NICO does not authorize exploitation, credential theft, phishing, malware, persistence, evasion, destructive actions, authentication bypass, or scanning without explicit permission. Production-impacting changes remain human decisions.

## Canonical data flow

```text
Authorized target
  → assessment intake
  → exact run identity and scope binding
  → repository evidence
  → isolated scanner worker
  → evidence attachment
  → evidence-bound scoring
  → repair and verification planning
  → draft report package
  → required human review
  → separately generated approved artifact
  → controlled delivery and receipt evidence
  → verification and repair memory
```

A later stage must not claim completion when its required upstream evidence is pending, unavailable, failed, mismatched, or unverified.

## Major components

### `nico/`

The Python package contains the defensive engine, assessment orchestration, scanner worker, evidence handling, persistence, scoring, reporting, review, delivery, governance, readiness, and operational APIs.

Key responsibilities include:

- authorization and scope enforcement
- repository-target normalization
- scanner execution and safe failure handling
- secret redaction and bounded output retention
- exact-run evidence attachment
- RYE-oriented repair prioritization
- TGRM-style repair candidate generation
- baseline and drift tracking
- verification and repair memory
- report generation and truth gates
- human-review and approved-artifact workflows
- production readiness and operational evidence

### FastAPI application

The production API registers assessment, scanner, report, review, delivery, readiness, recovery, and operations routes. API responses must distinguish among completed, pending, unavailable, failed, blocked, and human-review-required states.

### `apps/web/`

The Next.js application is the primary hosted operator interface. The normal assessment entry is the unified Express, Mid, and Full intake under `/assessment`.

Advanced operator pages remain separate when they require elevated identity, review decisions, delivery administration, recovery, diagnostics, or operational credentials. They are not alternative assessment-start paths.

### Persistence

NICO uses a storage facade with local SQLite support and production adapters where configured. Records may include runs, scanner evidence, reports, approvals, delivery grants, receipts, acknowledgments, operational events, baselines, drift, repairs, verification results, policy state, and audit history.

A response must disclose whether persistence is durable. An in-memory or failed write must not be represented as restart-safe.

## Assessment tiers

### Express

Express provides the fastest authorized repository baseline. It may use a narrower evidence set and returns a draft requiring human review.

### Mid

Mid binds repository and scanner evidence to one exact run and snapshot, then prepares a draft report and review request. It stops at human review.

### Full

Full runs the deepest configured evidence pipeline. It continues automatically through repository evidence, scanner execution, evidence attachment, scoring, report preparation, and final-review request creation when those stages are available. It stops at human review.

The tier controls depth and required evidence. It must not be used as a cosmetic label over the same unverified output.

## Scanner execution contract

The scanner worker:

- accepts only authorized GitHub repository targets
- clones into a temporary workspace
- uses `shell=False`
- applies repository-size and time limits
- checks binary and manifest availability
- redacts recognized secret patterns from retained output
- deletes the temporary workspace after completion
- records requested, executed, unavailable, failed, and timed-out tools separately

A requested scanner must either execute or appear explicitly as unavailable, failed, or timed out. It must not disappear silently from the evidence contract.

## Scoring and truth

Scores are evidence signals, not certifications. Missing evidence does not equal passing evidence. Pending or unavailable scanner records must not receive completion credit.

Reports must preserve:

- exact run and repository identity
- evidence provenance
- unavailable-data notes
- confidence limitations
- human-review requirement
- report and artifact hashes where applicable

## Review and delivery

Automated assessment ends at a human-review gate. Approval creates a separate approved artifact rather than mutating the reviewed draft. Client delivery requires a verified approved artifact, controlled access, and receipt evidence.

Admin tokens and raw delivery tokens must not be placed in URLs, cookies, browser storage, logs, reports, or build output. Delivery tokens may be returned once and passed through a URL fragment when required by the client workflow.

## Operations and release integrity

Operational readiness is stricter than HTTP reachability. Production readiness may require:

- frontend and backend deployment identity
- expected commit alignment
- durable storage
- required routes
- scanner execution capability
- truth guards
- runtime configuration
- event and alert persistence
- successful release-gate evidence

Unloaded operational data is neutral. It becomes a failure only after an authenticated load returns failed or unavailable evidence.

## Stable, advanced, and legacy surfaces

The current stable assessment start is `/assessment`.

Advanced surfaces include human review, delivery administration, recovery, diagnostics, readiness, and Retainer operations.

Legacy routes may remain temporarily for migration or recovery, but they must redirect normal users to the canonical workflow and must not create competing run identities.

See `docs/PROJECT_STATUS.md` for the current maturity map and `docs/OPERATOR_GUIDE.md` for operating procedures.
