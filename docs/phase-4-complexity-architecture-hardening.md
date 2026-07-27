# Phase 4: Complexity Reduction and Architecture Hardening

## Objective

Reduce the highest-risk complexity hotspots without changing report semantics, evidence requirements, client-delivery gates, or production behavior.

## Initial targets

- `_build_pdf`
- `_build_markdown`
- `_build_complexity`
- `build_comprehensive_report_package`
- `AssessmentWorkspace`
- `FinalReviewWorkspace`
- `FullRunPage`

## Work packages

1. Capture characterization tests before refactoring each hotspot.
2. Extract bounded pure helpers and smaller components with explicit inputs and outputs.
3. Preserve English and Spanish report parity.
4. Add complexity budgets and regression gates to CI.
5. Verify report structure, evidence provenance, terminal labels, and client-delivery policy remain unchanged.
6. Run the complete CI, production, scanner, security, mobile, iOS, resilience, and deployment matrix.
7. Generate a new Comprehensive report and compare complexity findings against the prior baseline.

## Merge policy

This phase must remain fail-closed. No hotspot is considered repaired merely because it is split into more files. Complexity metrics, test coverage, report equivalence, and production checks must all demonstrate improvement before merge.
