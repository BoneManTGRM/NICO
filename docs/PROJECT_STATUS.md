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
| Controlled delivery, receipts, and acknowledgments | Operational | Integrity-bound delivery controls exist. Production restart and durability evidence should be exercised regularly. |
| Operations readiness, events, and alerts | Operational | Semantic readiness is implemented. Operator usability and production evidence history should improve. |
| Retainer workflows | Experimental | Backend and operator surfaces exist; product contract and real-client fixtures are still developing. |
| Hosted SaaS multi-tenancy | Experimental | Scope and storage controls exist in parts; a complete commercial tenancy and billing product is not claimed. |
| Automatic production repair | Planned | NICO currently prepares repair plans and verification. It does not autonomously deploy production changes. |
| Legacy Full/Mid start pages | Legacy | Normal assessment starts must route through the unified assessment page. Advanced review and recovery surfaces remain separate. |
| CLI monolith | Legacy debt | Supported behavior remains, but core responsibilities should be extracted into services. |

## Current release truth

A release is considered deployable only when repository CI and the configured frontend/backend deployment checks pass for the intended commit. Deployment success does not prove an assessment run is correct; an authorized production smoke assessment is still required.

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

Completed major workstreams: **9 of 12**.

- [x] Canonical architecture, operator guide, maturity map, and documentation index.
- [x] Truthful README, security policy, contribution guidance, and repository templates.
- [ ] Deployed browser/API E2E proof for unified Express, Mid, and Full with exact-run identity and no duplicate starts.
- [x] Full-run metadata and route truth audit, including removal of stale Express/Mid wording.
- [x] External scanner contract: every requested tool executes or is explicitly unavailable, failed, or timed out.
- [x] Scanner result parsing and severity truth rather than exit-code-only approximation.
- [ ] CLI/service modularization across configuration, scanning, scoring, repair, drift, reporting, verification, and persistence.
- [x] Packaging and one-command local development, including supported `nico` and `nico-api` entry points.
- [x] Cross-module E2E coverage for assessment, report, review, approved artifact, controlled delivery, receipt, and acknowledgment.
- [ ] Restart, durable-storage, recovery, observability, and graceful-degradation proof.
- [x] Additional representative golden fixtures and recorded evidence-bound demonstrations with no fabricated live claims.
- [x] Public maturity boundaries for stable, operational, experimental, legacy, and planned areas.

## Remaining execution order

1. Deployed Express, Mid, and Full browser/API E2E proof.
2. Restart, persistence, observability, recovery, and graceful-degradation proof.
3. CLI and service modularization after behavior is protected by E2E and restart tests.

The remaining estimate is approximately **5–8 small, reviewable pull requests**, subject to defects uncovered during deployed and restart testing.

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
