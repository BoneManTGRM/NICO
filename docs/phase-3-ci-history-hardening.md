# Phase 3: CI Hardening and Historical Workflow Classification

## Objective

Make CI evidence decision-grade by separating genuine failures from expected cancellations, superseded runs, neutral/skipped outcomes, infrastructure faults, and policy violations. Historical workflow counts must never be presented as a single undifferentiated failure total.

## Work packages

### 3A. Deterministic run classification

Classify every non-successful workflow run into one of these machine-readable categories:

- `product_failure`
- `test_failure`
- `security_failure`
- `deployment_failure`
- `infrastructure_failure`
- `expected_cancellation`
- `superseded_run`
- `neutral_or_skipped`
- `manual_stop`
- `unknown_requires_review`

Every classification must retain workflow name, run ID, commit SHA, event, conclusion, timestamps, attempt, triggering actor, and a bounded reason.

### 3B. Fail-closed unknown handling

Unknown, missing, or contradictory metadata must be classified as `unknown_requires_review`, never silently counted as benign.

### 3C. Current-health separation

Historical outcomes must be reported separately from current branch health. A repository can have historical failures while the current required matrix is green; the report must show both facts without conflation.

### 3D. Workflow supply-chain hardening

Inventory every GitHub Action reference. Mutable tags must be pinned to immutable commit SHAs or explicitly dispositioned with a documented exception, owner, and expiry date.

### 3E. Dependency-update stability

Add or verify Dependabot cooldown/grouping behavior so newly released dependencies are not merged immediately without observation time and complete CI validation.

### 3F. Report integration

The Comprehensive report must show:

- total runs reviewed
- current required-check status
- counts by classification
- genuine unresolved failures
- expected cancellations/superseded runs
- unknown runs requiring review
- immutable-action-reference coverage
- dependency-update policy state

## Merge gate

Phase 3 is complete only when:

1. Historical non-success runs are deterministically classified.
2. Unknown cases fail closed and remain visible.
3. Current health is separated from historical reliability.
4. Action references are pinned or formally dispositioned.
5. Dependabot cooldown/grouping policy is enforced or explicitly documented.
6. Regression tests cover classification boundaries.
7. Full NICO CI and the complete production, scanner, security, CodeQL, mobile, iOS, resilience, and deployment matrix pass.
8. A new Comprehensive report no longer presents historical non-success runs as an undifferentiated failure count.
