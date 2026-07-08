# Evidence-Bound Score Lift Rules

This fixes the remaining 85/100 ceiling by applying score lifts only when the report already contains the required evidence.

## Static Analysis

Static Analysis can lift from yellow to green when:

- built-in static risk-pattern hits are zero
- no real blocking static finding remains
- CI/CD is green or includes lint/typecheck/build/test evidence

Unavailable external Semgrep, Bandit, ESLint, or TypeScript worker execution stays disclosed. It does not block the CI-backed static lift by itself.

## Secrets Review

Secrets Review can lift when parsed credential-scan and gitleaks evidence shows zero high-confidence credential findings.

Full git-history secret scanning still remains disclosed as unavailable until the sandboxed worker provides that proof.

## Velocity / Complexity

Velocity can lift when the core evidence set is green and PR/commit traceability is strong.

Velocity can lift further to release-readiness level only when code, dependency, secret, static, CI/CD, architecture, commit velocity, and PR traceability signals are all present.

## Boundary

These rules do not remove human review. They prevent evidence that is already present in the run from being ignored by the final scoring pass.
