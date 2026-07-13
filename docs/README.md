# NICO Documentation Map

Use this page to find the current authoritative document for an operating question.

## Canonical documents

- [`../ARCHITECTURE.md`](../ARCHITECTURE.md) — system boundaries, canonical data flow, major components, and truth contracts.
- [`OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md) — authorized assessment, recovery, review, delivery, and incident procedures.
- [`PROJECT_STATUS.md`](PROJECT_STATUS.md) — stable, operational, experimental, legacy, and planned maturity map.
- [`OPERATIONS_READINESS.md`](OPERATIONS_READINESS.md) — semantic production-readiness contract.
- [`PRODUCTION_RELEASE_GATE.md`](PRODUCTION_RELEASE_GATE.md) — exact-SHA deployment verification and rollback procedure.
- [`PRODUCTION_ASSESSMENT_SMOKE.md`](PRODUCTION_ASSESSMENT_SMOKE.md) — protected live Express/Mid/Full browser and API proof workflow.
- [`hosted-readiness-runbook.md`](hosted-readiness-runbook.md) — hosted evidence and readiness checks.
- [`NO_SERVER_ASSESSMENT.md`](NO_SERVER_ASSESSMENT.md) — local-first authorized assessment workflow.
- [`SAFARI_HOSTED_APP.md`](SAFARI_HOSTED_APP.md) — hosted browser deployment setup.

## Commercial and licensing documents

- [`license-faq.md`](license-faq.md)
- [`commercial-licensing-workflow.md`](commercial-licensing-workflow.md)
- [`commercial-license-order-form.md`](commercial-license-order-form.md)

## Historical and implementation notes

Files with version, patch, upgrade, remediation, handoff, or dated names are implementation history unless a canonical document links to them as a current contract.

Historical notes are useful for understanding why a control exists, but they must not be used to infer current production readiness, current routes, current scores, or current deployment state.

## Documentation rules

1. Update the canonical document when behavior changes.
2. Do not create another versioned architecture or operator guide.
3. Label synthetic examples and historical evidence explicitly.
4. Do not publish credentials, raw scanner secrets, private delivery tokens, or client data.
5. A feature claim must identify whether it is stable, operational, experimental, legacy, or planned.
