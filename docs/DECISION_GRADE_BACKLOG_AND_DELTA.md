# Decision-Grade Backlog and Historical Delta

NICO Comprehensive report packages now expose deterministic remediation backlog exports and an evidence-safe historical comparison contract.

These capabilities depend on `nico.decision_grade_contract.v1`. They do not create external issues, modify assessed repositories, or treat missing evidence as remediation.

## Backlog export contract

The backlog engine generates work from:

- 0–30 day roadmap work packages;
- unresolved P0 and P1 findings not already covered by a 0–30 day package;
- selected P2 findings when they are already part of a prioritized 0–30 day remediation package.

Findings that map to the same work package are consolidated into one issue. This prevents a single remediation from being duplicated across multiple scanner or report findings.

Every exported item contains:

- title and stable external ID;
- source finding IDs;
- problem statement;
- evidence references and retained locations;
- business impact;
- scope;
- implementation guidance;
- owner role and effort;
- dependencies;
- binary acceptance criteria;
- residual risk;
- source assessment and commit SHA;
- priority, classification, and labels;
- deterministic deduplication signature.

Supported outputs are:

- Markdown;
- versioned structured JSON;
- GitHub issue JSON;
- Jira-compatible CSV;
- Linear-compatible CSV.

The export package records SHA-256 hashes for each serialized format. `external_issue_creation_allowed` is always false in this phase. A later integration must require explicit authorization before creating issues in GitHub, Jira, or Linear.

## Historical delta compatibility

A comparison is permitted only when:

- the repository identity matches;
- the assessment type matches;
- the decision-grade schema family is compatible;
- the previous and current assessment IDs are different.

When no previous contract exists, NICO returns `no_comparable_previous_assessment`. It does not generate synthetic change language.

## Finding matching

Findings are matched by their stable fingerprint rather than report wording. Matching can therefore survive line-number changes and presentation changes when the durable control identity remains the same.

The delta engine classifies findings as:

- new;
- closed;
- reduced;
- unchanged;
- worsened;
- reopened;
- resolved by explicit status;
- not observed because required evidence disappeared or failed.

## Missing evidence is not closure

A finding from the previous assessment is not marked closed when the current assessment lacks the scanner or evidence category needed to observe it.

Instead, the delta records:

```text
not_observed_due_to_evidence_gap
```

and identifies the missing, failed, timed-out, stale, conflicted, partial, or permission-limited evidence source. This prevents scanner regression from appearing as technical improvement.

## Scanner comparison

Scanner changes are classified as:

- improved;
- regressed;
- unchanged;
- new scanner;
- scanner missing.

Required scanner failures are separately handled by the readiness contract and may produce `Evidence Incomplete` or `Delivery Blocked` depending on the complete validation result.

## Score and complexity changes

When prior and current assessment score payloads are available, the delta records:

- Technical Maturity score change;
- Evidence-Adjusted score change.

When compatible architecture evidence includes a retained cyclomatic-complexity measurement, the delta also records hotspot improvement, regression, or no change. A moved location is disclosed separately and is not treated as closure.

## Comprehensive report integration

The Comprehensive report package now includes:

- `backlog_export` in canonical JSON;
- Markdown, JSON, GitHub, Jira, and Linear backlog payloads;
- backlog hashes and item count;
- `historical_delta` in canonical JSON;
- a concise historical-delta Markdown artifact;
- report-quality assertions for unique backlog items and non-synthetic delta generation.

A previous contract can currently be supplied through `previous_decision_grade_contract` or `previous_contract`, with the prior assessment score payload in `previous_assessment`. Automatic durable lookup of the most recent compatible report remains a separate persistence integration step.
