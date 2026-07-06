# Scoring Accuracy v11

This update improves NICO Express scoring so report numbers move only when evidence interpretation becomes more accurate.

## What changed

- Secret-pattern hits are classified before scoring.
- Backend token variable references, docs examples, scanner rules, and test fixtures are not treated the same as confirmed leaks.
- Static-analysis hits are classified by source type before scoring.
- Scanner rule definitions and test-lab fixtures no longer carry the same penalty as production-source findings.
- Dependency OSV records from broad manifest ranges are labeled as broad-range warnings instead of confirmed installed-package vulnerabilities.
- Maturity score and semaphore are recalculated after accuracy polish.

## What did not change

- Human review is still required before client-facing delivery.
- Missing worker evidence is still disclosed.
- Full git-history secret scanning still requires a sandboxed worker.
- pip-audit, npm audit, Semgrep, Bandit, ESLint, and similar tools remain stronger evidence than hosted manifest-only review.

## Expected effect

For reports where low scores came mainly from false-positive or review-only evidence, the numbers should rise. For reports with confirmed production findings, the penalty remains.
