# NICO Project Status

This file is the canonical maturity map and completion roadmap for the current repository. A feature is not considered production-proven merely because code or unit tests exist.

## Status definitions

- **Stable**: canonical path, regression-covered, and expected to remain compatible.
- **Operational**: implemented and used, but production proof or usability work remains.
- **Experimental**: evidence of implementation exists, but contracts may change or coverage is incomplete.
- **Legacy**: retained only for compatibility, migration, recovery, or operator-only access.
- **Planned**: accepted work that is not complete.

## Current maturity map

| Area | Status | Current boundary |
|---|---|---|
| Defensive authorization and prohibited-action policy | Stable | Explicit permission remains mandatory. Production-impacting changes require human approval. |
| Local-first scanning and SQLite-backed repair memory | Stable | Local paths remain the lowest-dependency operating mode. |
| Unified Express/Mid/Full assessment intake | Operational | Canonical start path. Continued production E2E proof is required for every deployment change. |
| Express assessment | Operational | Produces an evidence-bound draft; human review remains required. |
| Mid assessment orchestration | Operational | Exact-run continuation, report preparation, and review request exist. Full-cycle production fixtures need expansion. |
| Full assessment orchestration | Operational | Repository evidence, scanner continuation, scoring, reports, and review request exist. Optional evidence may remain unavailable and must be disclosed. |
| Scanner worker | Operational | Real subprocess execution exists for supported tools. Requested tools execute or are disclosed as unavailable, failed, or timed out; production proof should continue. |
| RYE/TGRM repair planning | Operational | Repair prioritization and candidate generation exist; public validation and calibration remain separate work. |
| Drift, baseline, verification, and repair memory | Operational | Core workflows exist; long-running and real-world fixture coverage should expand. |
| Draft report generation | Operational | Representative synthetic golden fixtures and a deterministic recorded demonstration exist. Report-path consolidation remains work. |
| Human review and approved artifacts | Operational | Explicit review and separately generated approved artifacts exist. Cross-module E2E proof is protected by regression coverage. |
| Controlled delivery, receipts, and acknowledgments | Operational | Integrity-bound delivery controls exist. Postgres restart and same-ID recovery are exercised in CI; production restart drills remain recurring operator evidence. |
| Operations readiness, events, and alerts | Operational | Semantic readiness and bounded telemetry-degradation proof exist. Operator usability and live production evidence history should improve. |
| Retainer workflows | Experimental | Backend and operator surfaces exist; product contract and real-client fixtures are still developing. |
| Hosted SaaS multi-tenancy | Experimental | Scope and storage controls exist in parts; a complete commercial tenancy and billing product is not claimed. |
| Automatic production repair | Planned | NICO currently prepares repair plans and verification. It does not autonomously deploy production changes. |
| Legacy Full/Mid start pages | Legacy | Normal assessment starts must route through the unified assessment page. Advanced review and recovery surfaces remain separate. |
| CLI and local service architecture | Stable | Canonical configuration, scanning, governance, persistence, scoring, repair planning, drift, reporting, verification, and memory run through extracted modules. `nico.cli` remains only as a compatibility facade. |

## Current release truth

A release is considered deployable only when repository CI and the configured frontend/backend deployment checks pass for the intended commit. Deployment success does not prove an assessment run is correct; an authorized production smoke assessment is still required.

The latest verified deployed main commit is `3ca12001cea9ce3e17e5c5d23c904edd624d932b` (`Convert nico.cli into a compatibility facade (#386)`). Its configured Vercel and Railway deployment checks passed. This proves the modularized package and compatibility facade deployed successfully; it does not prove that any Express, Mid, or Full production assessment completed correctly. Deployed browser/API E2E proof remains incomplete until an authorized production smoke artifact and matching browser evidence are retained and reviewed.

## Claims NICO does not make

NICO does not claim:

- guaranteed vulnerability discovery
- certification or compliance attestation
- that unavailable scanners passed
- that a score proves security
- that generated repairs are safe to deploy without review
- that a draft report is approved or client-ready
- that synthetic fixtures are live production evidence
- that Reparodynamics is an independently validated academic discipline

## Completion roadmap

Completed major workstreams: **11 of 12**.

- [x] Canonical architecture, operator guide, maturity map, and documentation index.
- [x] Truthful README, security policy, contribution guidance, and repository templates.
- [ ] Deployed browser/API E2E proof for unified Express, Mid, and Full with exact-run identity and no duplicate starts.
- [x] Full-run metadata and route truth audit, including removal of stale Express/Mid wording.
- [x] External scanner contract: every requested tool executes or is explicitly unavailable, failed, or timed out.
- [x] Scanner result parsing and severity truth rather than exit-code-only approximation.
- [x] CLI/service modularization across configuration, scanning, scoring, repair, drift, reporting, verification, and persistence.
- [x] Packaging and one-command local development, including supported `nico` and `nico-api` entry points.
- [x] Cross-module E2E coverage for assessment, report, review, approved artifact, controlled delivery, receipt, and acknowledgment.
- [x] Restart, durable-storage, recovery, observability, and graceful-degradation proof.
- [x] Additional representative golden fixtures and recorded evidence-bound demonstrations with no fabricated live claims.
- [x] Public maturity boundaries for stable, operational, experimental, legacy, and planned areas.

## Remaining execution order

1. Execute and retain authorized deployed Express, Mid, and Full browser/API E2E proof.
2. Review the evidence package, reconcile exact frontend/backend commits and run identities, and record precisely what passed, failed, timed out, or remained unavailable.

The remaining core work is one controlled production-proof workstream, plus any defect corrections uncovered by that proof. Provider expansion remains blocked until the final roadmap item is completed.

## CLI/service modularization completion evidence

The completed modularization workstream is bounded to the local CLI and service architecture:

- `nico.cli_entrypoint` is the canonical parser and dispatcher.
- Runtime paths are resolved by `nico.local_runtime_config` without database or network work in that module body.
- Local scanning, governance, SQLite persistence, scoring and repair planning, reporting, verification, and memory are implemented in narrow extracted modules.
- `nico.cli` is a compatibility facade that preserves legacy imports and constructor behavior without duplicating scanner, schema, report, verification, memory, or parser implementations.
- Package entrypoint, full test suite, integrity, CodeQL, audit, remediation, resilience, Postgres restart, and recorded-golden workflows passed for the facade conversion.
- Main commit `3ca12001cea9ce3e17e5c5d23c904edd624d932b` passed the configured Vercel and Railway deployment checks.

This completion does not prove a live assessment, approve or apply a repair, authorize production changes, or permit client delivery.

## Resilience completion evidence

The completed resilience workstream is bounded to repository and ephemeral-CI proof:

- `.github/workflows/postgres-restart-proof.yml` exercises NICO's real Postgres adapter and proves critical assessment, scanner, evidence, report, approval, and audit records survive fresh adapter instances with tenant and run identity preserved.
- `.github/workflows/resilience-proof.yml` exercises stale scanner reconciliation, persisted `recovery_required` state, explicit same-ID resume, duplicate-resume idempotency, memory-fallback blocking, and bounded redacted telemetry degradation.
- `scripts/postgres_restart_proof.py` and `scripts/build_resilience_proof.py` emit synthetic, non-live evidence artifacts without database URLs, credentials, automatic repair authority, approval, or client-delivery authority.
- Scanner recovery remains operator-controlled; no automatic resume or production-impacting action is authorized by these proofs.

This completion does not claim that Railway restarted, a production backup was restored, or a live client assessment recovered after an outage. Those remain recurring production-operations drills rather than repository completion blockers.

## Golden-fixture completion evidence

The completed golden-fixture workstream is bounded to synthetic, non-live evidence:

- `tests/fixtures/golden/manifest.json` governs unavailable-evidence, complete-evidence, and mixed-risk repair scenarios.
- Every fixture remains review-required, unapproved, non-client-ready, non-certifying, and delivery-blocked.
- `.github/workflows/recorded-golden-demonstration.yml` builds the suite twice, requires byte-for-byte reproducibility, and uploads bounded JSON and Markdown artifacts.
- `scripts/build_golden_demonstration.py` fails closed on unsafe paths, coverage drift, duplicate identities, live claims, weakened review or delivery boundaries, certification claims, and automatic production-change permission.

This completion does not count as deployed browser/API E2E proof or live production evidence.

## Phase 2 gate

Repository-provider expansion remains deferred until the completion roadmap above is finished and production-proven. The intended order is provider-neutral contract, GitHub parity adapter, GitLab, Bitbucket, Azure DevOps, Gitea/Forgejo, then generic Git.

This document is the authoritative tracker. GitHub issues are reserved for actionable defects or bounded implementation work rather than long-lived roadmap bookkeeping.
