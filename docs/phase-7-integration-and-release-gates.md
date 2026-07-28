# Phase 7 integration and release gates

This document is the umbrella control record for PRs #904, #905, and #906.

## Non-negotiable truth rules

1. No missing applicable evidence may be represented as complete.
2. No score may redistribute missing control weight into technical maturity.
3. No P0 may be published from a scanner candidate without verified or reproduced evidence.
4. No unresolved template token, duplicate finding, duplicate acceptance criterion, or contradictory score may reach a client surface.
5. Every report surface must be generated from one immutable final truth object.
6. Every repository, scanner, CI, deployment, and provider record must bind to the exact assessed revision.
7. Unknown provider states remain unknown and require review. They are never mapped to success.
8. Degraded evidence always blocks client delivery.

## Dependency order

- PR #904 owns canonical truth, scoring, finding identity, verification status, report state, and cross-format parity.
- PR #905 owns scanner execution, exact-revision evidence, CI classification, artifact retention, retry policy, and evidence finalization.
- PR #906 owns provider-neutral repository and pipeline evidence plus provider capability limitations.
- This umbrella branch owns only final integration, complete regression assessments, release proof, and merge sequencing.

## Required integration sequence

1. Rebase the three implementation PRs on the same main revision.
2. Integrate PR #906 provider identity into PR #905 evidence records.
3. Integrate PR #905 evidence decision into PR #904 score ledger and approval state.
4. Route every JSON, CSV, Markdown, HTML, PDF, and API surface through the frozen PR #904 truth object.
5. Generate fresh exact-revision assessments of NICO and ARA.
6. Compare generated reports against repository evidence and retained raw artifacts.
7. Repair all discrepancies before release consideration.

## Required end-to-end proof

A release candidate is blocked unless all of the following are retained and green:

- Python tests and coverage
- frontend typecheck and production build
- Docker build and startup proof
- Bandit
- Semgrep
- ESLint
- TypeScript
- Gitleaks
- TruffleHog
- pip-audit
- npm audit where applicable
- OSV scanner
- exact-revision CI status capture
- provider conformance fixtures
- English report generation
- Spanish report generation
- JSON/CSV/Markdown/HTML/PDF truth parity
- rendered PDF inspection
- duplicate and placeholder scan
- filename idempotence
- client-delivery blocking when evidence is incomplete

## Acceptance fixtures

### ARA

The prior ARA result is a required scoring regression fixture. The system must show distinct observed, coverage-adjusted, and evidence-adjusted values. Missing Static Analysis may not produce an overall 83 maturity score by normalization.

### NICO

The prior Comprehensive report is a required report-integrity fixture. Duplicate findings, repeated acceptance criteria, generic placeholder titles, `location-not-retained`, duplicated filename states, and contradictory scanner completion must all fail generation.

## Merge policy

All four PRs remain draft and unmerged until the implementation PRs are complete, the combined release candidate passes every gate above, the generated reports are inspected, and the user explicitly authorizes merging.
