# NICO Project Status

This file is the canonical maturity map for the current repository. A feature is not considered production-proven merely because code or unit tests exist.

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
| Scanner worker | Operational | Real subprocess execution exists for supported tools. Requested-tool completeness and result parsing are active hardening work. |
| RYE/TGRM repair planning | Operational | Repair prioritization and candidate generation exist; public validation and calibration remain separate work. |
| Drift, baseline, verification, and repair memory | Operational | Core workflows exist; long-running and real-world fixture coverage should expand. |
| Draft report generation | Operational | Multiple output paths exist. Report-path consolidation and golden fixtures remain work. |
| Human review and approved artifacts | Operational | Explicit review and separately generated approved artifacts exist. Cross-module E2E proof should expand. |
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

## Active roadmap

The active workstreams are tracked in GitHub issue #340. This file should be updated when a workstream changes maturity, not for every implementation commit.
