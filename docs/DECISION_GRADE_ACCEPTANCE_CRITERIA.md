# Decision-Grade Acceptance Criteria

Version: `nico.decision_grade_acceptance.v1`

## Purpose

Recommendations are not executable unless completion can be proven. NICO therefore stores acceptance criteria as typed, binary verification records rather than relying on unvalidated report prose.

The acceptance engine runs after Cost of Inaction processing and before the consistency engine. This order allows the final consistency gate to validate the completed criteria set.

## Hybrid generation model

The engine uses three stages:

1. Deterministic templates for known finding categories.
2. Optional contextual criteria supplied in `drafted_acceptance_criteria`.
3. Deterministic validation before any criterion is retained.

Contextual drafting can improve wording and specificity, but it cannot bypass the validation rules.

## Required criterion properties

Every retained criterion requires:

- a specific measurable end state;
- a validation method;
- an immutable target commit SHA;
- a durable evidence anchor;
- a binary comparator and target;
- required verification evidence;
- a pending, pass, fail, or not-applicable state.

Supported durable anchors include:

- repository-relative file path plus symbol or control;
- named test;
- named workflow;
- configuration key;
- metric;
- repository query;
- dependency identifier;
- stable control identifier.

Line numbers remain assessment-time evidence references. They are not accepted as the only durable anchor.

## P0 and P1 coverage

Every P0 or P1 receives at least three independently verifiable criteria:

1. Implementation or control end state
2. Named automated-test verification
3. Named workflow or CI verification

The engine records `priority_acceptance_coverage_incomplete` as a critical issue when this coverage cannot be created and verified.

P2 and P3 findings require at least one valid implementation or control criterion but do not automatically receive the three-part P0/P1 set.

## Deterministic templates

### Architecture

Default end state:

```text
cyclomatic_complexity <= 30
```

The criterion is anchored to the durable repository path and symbol or architecture control.

### Dependency

The release-blocking condition must be absent from the locked dependency graph. Verification requires the locked graph and dependency-scanner result.

### Secret history

No confirmed live credential matching the retained sanitized fingerprint may remain in the authorized repository history.

### CI/CD

The release-validation control must record zero unresolved blocking failures, and the configured validation workflow must pass on the target commit.

### Static analysis and code risk

The confirmed analyzer fingerprint must be absent at the durable file or control anchor on the target commit.

### Evidence or scanner reliability

The required scanner must complete without timeout, permission failure, conflict, stale evidence, or partial status.

### Generic controls

The affected control must record a binary pass against the immutable target commit.

## Contextual draft input

Contextual criteria may be supplied in the assessment payload:

```json
{
  "drafted_acceptance_criteria": {
    "RISK-P1-EXAMPLE": [
      {
        "description": "The named module records zero unresolved lifecycle threshold violations.",
        "validation_method": "metric_comparison",
        "file_path": "apps/web/app/assessment/AssessmentWorkspace.tsx",
        "symbol_or_control": "AssessmentWorkspace",
        "metric": "unresolved_lifecycle_threshold_violations",
        "comparator": "=",
        "target_value": 0,
        "required_evidence": [
          "Complexity scanner result",
          "Validation commit SHA"
        ]
      }
    ]
  }
}
```

Keys may use the stable NICO finding ID or the retained source finding ID.

Invalid contextual criteria are discarded. NICO records `acceptance_criterion_replaced` and generates a deterministic replacement when possible.

## Validation configuration

The assessment payload may provide:

```json
{
  "acceptance_validation_commit_sha": "<validation commit SHA>",
  "acceptance_workflow_name": "NICO CI"
}
```

When no separate validation SHA is supplied, the assessed immutable commit is used as the initial rerun context. The criterion remains pending until verified against an appropriate remediation or validation commit.

## Rejected language

The engine rejects or replaces vague statements such as:

- Improve the architecture
- Add more tests
- Refactor the frontend
- Make CI reliable
- Review security
- Address technical debt

A polished sentence is not sufficient. The criterion must have a durable anchor, a binary result, and evidence required to prove that result.

## Roadmap integration

Roadmap work packages mapped to P0/P1 findings receive a binary workflow criterion when none exists. Work-package criteria retain the same immutable target-commit and evidence requirements as finding criteria.

## Output

The final criteria are stored in the canonical contract and therefore flow into:

- structured JSON;
- detailed report findings;
- six-month roadmap packages;
- PDF, Markdown, and HTML;
- backlog exports;
- historical remediation verification.

The assessment also receives `decision_grade_acceptance`, which reports:

- target commit SHA;
- workflow name;
- total criteria;
- deterministic criteria generated;
- contextual/source criteria rejected;
- P0/P1 three-part coverage;
- whether binary results are required.
