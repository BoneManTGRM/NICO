# Decision-Grade Contradiction and Consistency Engine

Version: `nico.decision_grade_consistency.v1`

## Purpose

A report is not safe for external review merely because its Markdown, HTML, JSON, CSV, and PDF files rendered. The consistency engine validates the canonical decision-grade contract after cost-of-inaction processing and before report-view projection.

Validation results remain machine-readable in `DecisionGradeContract.validation_issues` and in the assessment field `decision_grade_consistency`.

## Deterministic checks

### Identity and evidence

- Direct and derived evidence must use the immutable assessed commit SHA.
- External evidence may use a different source identity only when explicitly marked externally supplied.
- Finding evidence references must resolve to canonical evidence records.
- Temporary, absolute, and unresolved locations are rejected or warned as non-durable evidence anchors.
- P0/P1 findings require at least one completed evidence record.

### Risk inventory

- Finding and evidence IDs must be unique.
- Executive findings must resolve to canonical findings.
- Resolved findings are removed from the active Executive Risk Register.
- The next highest-ranked active findings are promoted deterministically.
- The Executive Risk Register remains capped at seven.

### Recommendations, roadmap, and ownership

- P0/P1 findings require roadmap and backlog mappings.
- Recommendations and acceptance criteria must be present.
- Roadmap work packages must map to real findings.
- Roadmap work packages require acceptance criteria.
- A differing finding owner and work-package owner is visible unless the finding owner is recorded as a supporting role.

### Score truth

For included scored controls, the engine recalculates:

```text
weighted contribution = technical score × control weight
technical maturity = round(sum(weighted contributions) / sum(active weights))
```

It detects:

- missing score arithmetic inputs;
- weighted-contribution mismatch;
- reported Technical Maturity mismatch;
- a Technical Maturity score with no included controls;
- Technical Maturity and Evidence-Adjusted fields swapped;
- Evidence-Adjusted score greater than Technical Maturity.

### Scanner confidence and decision posture

The engine detects:

- high-confidence findings whose evidence category is constrained by a partial, failed, timed-out, stale, conflicted, or permission-limited scanner;
- Release marked positively while an open release blocker exists;
- Release marked positively despite incomplete required scanner evidence;
- Client Delivery marked positively despite incomplete required scanner evidence;
- release postures that omit open blocking finding IDs.

### Cost integrity

Any quantitative cost-of-inaction record must retain disclosed assumptions. Monetary values remain subject to the stricter Pydantic validation in the canonical contract and the deterministic cost engine.

## Readiness behavior

- Any critical contradiction sets `Delivery Blocked`.
- Incomplete required scanner evidence sets `Evidence Incomplete` unless a critical issue is present.
- Noncritical errors retain `Human Review Required`.
- Warnings remain visible but do not independently authorize or block delivery.
- The engine never promotes a generated report to `Client Ready`.

Human approval and approved-artifact verification remain separate, existing controls.

## Scope boundaries

The engine validates internal contract consistency. It does not claim to:

- execute a penetration test;
- validate production runtime behavior;
- resolve whether business assumptions are commercially correct;
- replace a named human reviewer;
- verify a repository file exists when the immutable source archive is unavailable to the report process.

Repository-location existence checks should be added at the evidence-collection boundary where the immutable snapshot is directly accessible.
