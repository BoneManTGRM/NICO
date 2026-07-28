# Phase 10 Real Assessment Validation Contract

Phase 10 validates the merged production assessment path against real repositories and independent human review. It does not expand marketing claims.

## Validation targets

1. NICO self-assessment on an immutable commit.
2. Multiple unrelated repositories representing different languages, sizes, build systems, and maturity levels.
3. At least one repository with Python code so the exact-revision Bandit path is exercised.
4. At least one repository where ESLint is configured and one where it is truthfully not applicable.

## Required retained artifacts per target

- repository identity and immutable commit SHA
- run identity and timestamps
- scanner execution records, commands, versions, exit codes, findings counts, stderr, and artifact hashes
- canonical JSON
- canonical findings CSV
- English PDF
- Spanish PDF
- release-gate result
- normalized filenames
- approval state and client-delivery state
- exact-package manifest and SHA-256 fingerprint

## Human comparison ledger

Each automated finding must be classified as confirmed, disputed, false positive, duplicate prevented, or not independently reviewed. Human-only findings must be recorded as possible false negatives. Track severity agreement, source-location agreement, remediation usefulness, and evidence sufficiency.

## Bandit acceptance

Bandit is accepted only when the exact-revision execution record proves completion. Exit code 0 means completed without findings. Exit code 1 means completed with findings. Missing output, malformed JSON, wrong revision, unsupported invocation, or execution errors fail closed.

## Report acceptance

The same canonical finding population must drive executive findings, detailed findings, roadmap, backlog, remediation surfaces, JSON, CSV, and both language editions. Validation fails for duplicate findings, duplicate acceptance criteria, generic priority titles, placeholders, language mismatch, inconsistent counts, or repeated terminal-state filename tokens.

## Claim boundary

Phase 10 evidence may support measured statements about tested repositories. It may not support a claim that NICO replaces a premium consulting engagement until unrelated-repository validation and independent review meet documented thresholds.

## Exit criteria

- all Phase 10 checks green on the exact branch revision
- validation artifacts retained for every target
- human comparison ledger complete
- aggregate precision, recall proxy, severity agreement, and remediation usefulness reported with limitations
- explicit release recommendation or rejection
