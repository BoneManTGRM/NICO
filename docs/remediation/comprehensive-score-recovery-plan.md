# NICO comprehensive score recovery plan

## Objective

Raise NICO's technical-maturity and evidence-adjusted scores through verified engineering improvements. Scores must never be edited directly, scanner findings must never be hidden, and unknown evidence must remain review-required until dispositioned.

## Non-negotiable truth rules

1. No manual score overrides or cosmetic score inflation.
2. No broad Bandit rule skips.
3. No broad Gitleaks path, rule, regex, or commit allowlists.
4. Test, fixture, generated, vendor, and build-output observations remain visible but do not count as production defects.
5. A secret candidate is material only when the evidence identifies an active secret in current production-relevant content.
6. A dependency candidate is material only when package, installed version, advisory, fixed version, dependency path, production scope, and reachability are established.
7. Every report format must use the same canonical score, scanner, finding, identity, lifecycle, and approval fields.
8. No PR merges with an unresolved failed workflow or an uninspected final PDF artifact.

## Phase 1: scanner and artifact correctness

- Remove dynamic execution and secret-like literals from synthetic test fixtures.
- Enforce strict production-scoped Bandit scanning with no skipped rules.
- Enforce default Gitleaks rules with no broad allowlists.
- Separate current-tree secret scanning from full-history evidence collection.
- Normalize the final PDF lifecycle suffix exactly once.
- Add production guards against eval, exec, disabled TLS verification, and insecure frontend transport flags.

Acceptance:

- Bandit production scan completes successfully or retains exact-location production findings.
- Current-tree Gitleaks scan completes successfully or retains exact-location active findings.
- Full-history findings remain retained and explicitly dispositioned.
- No duplicated `FINAL-PENDING-APPROVAL` suffix.
- Full exact-head workflow matrix passes.

## Phase 2: secrets disposition and evidence assurance

- Preserve each Gitleaks and TruffleHog record separately.
- Record detector/rule, path, line, commit, fingerprint, current-tree status, production scope, verification state, and remediation.
- Classify each record as verified material, historical review, non-production observation, revoked/rotated, or triage required.
- Apply technical-score impact only to verified current production exposure.
- Apply assurance impact to unresolved historical or ambiguous records.

Acceptance:

- No raw candidate count is presented as a confirmed secret defect count.
- No secret is printed in logs, reports, artifacts, or comments.
- Every retained candidate has a stable fingerprint and disposition.

## Phase 3: dependency remediation

- Export every OSV advisory with package, installed version, fixed version, dependency path, severity, scope, and reachability.
- Upgrade direct vulnerable dependencies first.
- Regenerate lockfiles with the package manager rather than editing resolved versions manually.
- Rerun npm-audit, pip-audit, and OSV on the same immutable revision.
- Retain transitive or unreachable candidates as assurance-limited until proven material.

Acceptance:

- No dependency receives material score impact without complete disposition evidence.
- Builds, tests, TypeScript, ESLint, and production deployment proofs remain green after upgrades.

## Phase 4: production complexity and CI reliability

- Refactor the highest-value active production hotspots before report-only or test-only modules.
- Add characterization tests before decomposing branch-heavy functions and components.
- Classify bounded CI non-success runs as genuine code failure, infrastructure fault, expected cancellation, neutral/skip, or unknown review required.
- Fix recurring genuine failures and publish a rolling reliability trend.

Acceptance:

- Reduced cyclomatic complexity and branch concentration are measured on a fresh exact-SHA scan.
- No test coverage, user flow, scanner, or deployment regression.
- Historical CI evidence remains separate from assessed-commit health.

## Phase 5: report and score verification

- Generate a fresh full Comprehensive assessment from the final merged commit.
- Verify all scanner truth, score aliases, findings, status language, filenames, and PDF table layouts.
- Confirm English and Spanish parity.
- Visually inspect the complete final PDF, not only a reduced fixture.
- Require two consecutive production acceptance passes.

Completion criteria:

- All workflows green on the exact final commit.
- No scanner contradiction, stale score mismatch, false production finding, table overlap, duplicate suffix, hidden control character, or lifecycle contradiction.
- Any score increase is traceable to a fixed defect, completed disposition, increased evidence assurance, or measured complexity/reliability improvement.
