# Decision-Grade Strategic Human Evidence

Version: `nico.decision_grade_human_evidence.v1`

## Purpose

Repository analysis cannot prove functional behavior, device parity, stakeholder priorities, incident history, product constraints, regulatory obligations, staffing capacity, or formally accepted risk. NICO therefore stores those facts in a separate human-evidence ledger and never infers them from source code or scanner output.

## Modules

The ledger contains ten explicit modules:

1. Functional QA
2. Browser, device, and platform parity
3. Accessibility and UX review
4. Stakeholder objectives and constraints
5. Incident and support history
6. Product objectives and release outcomes
7. Release deadlines and delivery constraints
8. Regulatory and contractual requirements
9. Budget, staffing, and capacity constraints
10. Known decisions and accepted risks

## Status model

Each module is exactly one of:

- `complete`: all required evidence fields and reviewer metadata are retained;
- `partial`: some evidence exists but required evidence or metadata is missing;
- `not_assessed`: no authorized human evidence was supplied;
- `excluded`: the module is explicitly outside scope and a rationale is retained.

A completed module requires:

- every module-specific required field;
- named reviewer;
- observation timestamp;
- source reference.

An exclusion without rationale remains partial and cannot be presented as an approved scope exclusion.

## Readiness behavior

Partial or not-assessed Strategic modules add `human_evidence_incomplete` and constrain the decision-grade contract to `Evidence Incomplete`, unless a stronger Delivery Blocked state already exists.

The ledger never promotes a report to Client Ready. Human review remains required and client delivery remains disabled.

## Inputs

Human evidence may be supplied through `identity.human_evidence_inputs` or a `human_evidence_intake` stage. The intake accepts module-keyed dictionaries or the generated intake-template structure.

## Exports

The report package includes:

- structured human-evidence ledger;
- deterministic JSON ledger;
- intake-template JSON;
- Functional QA CSV;
- platform parity CSV;
- stakeholder decision-log CSV;
- SHA-256 hashes for every export.

The ledger is also projected into Markdown and HTML. Missing evidence is displayed directly rather than silently omitted.

## Guardrail

Human, QA, parity, accessibility, incident, product, compliance, budget, and risk-acceptance claims are retained only when explicitly supplied or observed. Repository code is never used to fabricate these facts.
