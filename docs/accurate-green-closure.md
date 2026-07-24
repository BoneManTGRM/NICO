# Accurate Green Closure Contract

NICO must not make a control green by changing a color, lowering a threshold, suppressing a scanner, or treating missing evidence as clean.

A scored control is **verified green** only when both conditions are true:

1. The evidence-backed technical score is at least 80/100.
2. Evidence assurance is `VERIFIED` and the canonical risk disposition is `GREEN`.

Human approval and client-delivery authorization remain separate from technical green.

## Current Express closure requirements

### Dependency / Library Ecosystem

- Preserve the clean pip-audit and npm-audit artifacts.
- Triage the retained OSV candidate against the exact package, version, and immutable commit.
- Repair a confirmed vulnerability or record a signed false-positive/not-affected disposition.
- Rerun all dependency analyzers on the same exact commit and retain the artifact hashes.

### Secrets Exposure Review

- Complete Gitleaks without timeout for the full history scope.
- Review every consolidated Gitleaks and TruffleHog candidate by rule, exact location, commit, and redacted fingerprint.
- Remove or rotate confirmed credentials and document synthetic/test/example findings.
- Rerun both history scanners and retain a clean or fully triaged exact-run artifact.

### Static Analysis

- Complete Bandit execution and preserve its canonical exit disposition.
- Configure and execute a real ESLint analyzer; TypeScript compilation must remain separate.
- Triage Semgrep, TypeScript, Bandit, and ESLint findings by rule, severity, exact location, and disposition.
- Repair confirmed issues, approve only evidenced false positives, and rerun the exact snapshot.

### Velocity / Complexity

- Close the final-clean dependency, secret, static-analysis, and CI evidence prerequisites.
- Reduce or explicitly accept the highest verified complexity/churn hotspots with focused regression tests.
- Recompute the score from the repaired exact snapshot. The green threshold remains 80.

## Presentation contract

- Technical score color comes only from the score band.
- Evidence assurance is displayed as a separate badge or field.
- Canonical risk disposition remains visible and unchanged.
- Markdown, HTML, JSON, PDF, and the live UI must show the same score, band, assurance, and disposition.
- Reports must include the exact unmet conditions for every control that is not verified green.
