# Decision-Grade Assessment Contract

NICO decision-grade reports use `nico.decision_grade_contract.v1` as the canonical structured contract for report validation, historical comparison, backlog generation, and delivery-readiness decisions.

This contract supplements the existing assessment and report schemas. It does not replace raw evidence or authorize delivery.

## Four-layer truth model

Every material conclusion must remain distinguishable as one of four layers:

1. **Evidence** — directly collected or externally supplied facts bound to the assessed commit.
2. **Interpretation** — a technical conclusion derived from one or more evidence records.
3. **Business inference** — a likely effect on release, reliability, velocity, maintenance, staffing, or customer outcomes.
4. **Recommendation** — an owned action with effort, sequencing, acceptance criteria, expected impact, and residual risk.

A business inference must not be presented as direct evidence.

## Canonical entities

The contract contains:

- assessment identity;
- evidence records;
- stable findings and fingerprints;
- structured acceptance criteria;
- cost-of-inaction records;
- residual-risk records;
- roadmap work packages;
- scanner execution records;
- assumptions;
- separate operate, release, client-delivery, and human-review postures;
- machine-readable validation issues;
- a readiness status.

## Stable finding identity

Finding identity is derived from durable attributes such as category, control or title, scanner identity, and file or control location. Line numbers are intentionally removed from the fingerprint so ordinary edits do not create a new risk identity solely because code moved within a file.

The normalized identifier format is:

```text
RISK-<PRIORITY>-<FINGERPRINT_PREFIX>
```

The original source finding identifier remains available separately.

## Executive Risk Register

The executive register is capped at seven findings in code. Additional findings remain in the detailed register and appendix. Ranking is deterministic and considers:

- release-blocking status;
- priority;
- category override for direct security and release risks;
- confidence;
- stable finding identity.

Writing order and rhetorical intensity do not determine rank.

## Acceptance criteria

P0 and P1 findings require structured, binary acceptance criteria. Each criterion includes:

- a validation method;
- the target commit context;
- a durable file, symbol, workflow, configuration, metric, dependency, query, or control anchor;
- required verification evidence;
- a pass/fail state.

Free-form recommendations without verifiable criteria do not satisfy the decision-grade contract.

## Cost of inaction

NICO supports three modes:

1. `client_input` — uses client-supplied operating and financial values;
2. `scenario` — uses disclosed low, base, and high assumptions;
3. `qualitative` — uses Minimal, Limited, Material, Severe, or Critical exposure without a monetary claim.

Monetary values require a currency and disclosed assumptions. When client financial inputs are unavailable, the current adapter uses qualitative exposure and explicitly states that no monetary amount is claimed.

## Residual risk

Every normalized finding records:

- what remediation reduces;
- what it does not eliminate;
- remaining likelihood and impact;
- monitoring requirements;
- possible follow-on work;
- confidence.

Residual risk is not assumed to be zero.

## Readiness statuses

Supported statuses are:

- Internal Draft
- Evidence Incomplete
- Human Review Required
- Conditionally Deliverable
- Client Ready
- Delivery Blocked

The current automated Comprehensive pipeline stops at `Human Review Required` when structural validation succeeds. It cannot set `Client Ready` without a separate approved-artifact and human-review workflow.

Critical structural contradictions, unsupported benchmark language, invalid commit identity, score inversion, or failed PDF generation produce `Delivery Blocked`. Required scanner failures produce `Evidence Incomplete` unless a more severe validation failure exists.

## Current integration

The Comprehensive report package now includes:

- `decision_grade_contract` in the top-level result;
- `decision_grade_contract` in the report package;
- the contract inside canonical JSON;
- `delivery_status` derived from the contract;
- contract quality metrics in `report_quality_contract`.

The report-generation status and client-delivery status remain separate. A report may render successfully while delivery remains blocked or pending human review.

## Planned dependent work

The contract is the foundation for:

- first-class historical delta matching;
- GitHub, Jira, Linear, JSON, and Markdown backlog exports;
- stronger scanner completeness calculations;
- contradiction checks across all report formats;
- report-readiness promotion after recorded human approval;
- scope-adjusted Express and Mid contracts;
- executive-brief one-page regression checks.
