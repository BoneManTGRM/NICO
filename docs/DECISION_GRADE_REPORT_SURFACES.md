# Decision-Grade Report Surfaces

NICO Comprehensive reports project the canonical `nico.decision_grade_contract.v1` into every client-facing and machine-readable report surface.

The structured contract remains the source of truth. Markdown, HTML, PDF, and findings CSV are presentation views of that contract rather than independent sources of risk identity, cost exposure, residual risk, or delivery posture.

## Two-pass rendering boundary

The report pipeline uses a bounded multi-pass process:

1. Render the existing reconciled assessment to establish an initial PDF boundary.
2. Build and validate the canonical decision-grade contract.
3. Project stable findings, roadmap work packages, evidence health, assumptions, scope boundaries, and decision postures into the assessment view.
4. Re-render Markdown, HTML, and PDF using the structured view.
5. Rebuild the contract against the actual decision-grade PDF page boundary.
6. Render the final package from the final structured view.

Successful rendering does not produce `Client Ready`. Delivery status remains controlled by the readiness contract and human approval workflow.

## Executive Risk Register

All client-facing Executive Risk Registers now use the contract’s deterministic seven-item selection.

Each row contains:

- priority;
- stable risk ID;
- risk;
- business impact;
- confidence;
- recommended action;
- effort;
- cost of inaction;
- residual risk;
- evidence locations.

Additional findings remain in the detailed register and evidence appendix.

## Four-layer finding presentation

Every detailed finding is rendered as:

1. Evidence or direct fact
2. Technical interpretation
3. Business inference
4. Recommendation

The same record also shows owner, effort, acceptance criteria, cost-of-inaction mode and assumptions, residual risk, roadmap mapping, and backlog mapping.

## Evidence health

The report includes a structured Evidence Health Summary containing:

- completed scanners;
- incomplete scanner records;
- required status;
- affected evidence categories;
- confidence effect;
- remediation guidance.

A missing or failed evidence source cannot be visually buried in the appendix.

## Roadmap

Roadmap presentation uses the contract’s normalized work packages. It includes:

- stable work-package ID;
- Quick Win or Strategic classification;
- related risk IDs;
- owner and supporting roles;
- effort range;
- dependencies;
- implementation sequence;
- binary acceptance criteria;
- expected technical and business impact;
- residual risk.

## Scope and assumptions

Markdown, HTML, and PDF now include:

- How to Use This Report;
- Scope Boundary and Unassessed Risk;
- Assumption Register;
- Human Review and Acceptance Gate.

Unassessed domains are explicitly prevented from being interpreted as healthy. Financial exposure remains qualitative unless client inputs or disclosed scenario assumptions support a monetary estimate.

## Regression checks

The report-surface tests verify:

- exactly seven executive risks are presented;
- stable IDs appear on every executive risk;
- cost of inaction and residual risk are present;
- evidence health, scope boundaries, assumptions, and operating instructions render;
- detailed findings preserve all four truth layers;
- the PDF renders successfully;
- the Executive Decision Brief remains isolated from the following Technical Scorecard page.
