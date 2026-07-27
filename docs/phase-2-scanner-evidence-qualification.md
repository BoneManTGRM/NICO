# Phase 2: Scanner Reliability and Evidence Completeness

## Objective

Make scanner evidence client-ready only when every required scanner completes on the exact target commit, its complete redacted raw output is retained, provenance is verified, and two consecutive frozen-SHA runs produce equivalent deterministic fingerprints.

## Required scanners

- pip-audit
- npm-audit
- osv-scanner
- bandit
- semgrep
- eslint
- typescript
- gitleaks
- trufflehog

## Phase 2 work packages

### 2A. Explicit readiness diagnostics

Add a machine-readable readiness summary that identifies each blocking scanner and the exact reason it is not verified. Missing, unavailable, failed, timed-out, truncated, unretained, or provenance-mismatched evidence must never be represented as clean.

### 2B. Per-tool artifact integrity

Require every scanner to provide a redacted retained artifact with a verified SHA-256 checksum, non-empty format metadata, and a stable storage key. A completed scanner without retained evidence must be downgraded to failed evidence.

### 2C. Exact-commit provenance

Require target repository, target commit, application commit, checkout commit, and workflow release identity to be recorded and reconciled. Any mismatch blocks client readiness.

### 2D. Repeatability qualification

Run the complete scanner suite twice against the same frozen commit. Require the same required-tool set, completed statuses, retained-artifact coverage, and deterministic fingerprints in both runs.

### 2E. Report integration

Expose scanner readiness, blocking tools, capture completeness, provenance state, and repeatability state in the Comprehensive report. Do not show a scanner section as complete when evidence is partial.

## Merge gate

Phase 2 is complete only when:

1. All required scanners complete twice on the same frozen SHA.
2. Every required raw artifact is retained and checksum-verified.
3. Exact-commit provenance is verified.
4. Deterministic fingerprints match across both runs.
5. Full NICO CI, production acceptance, security, CodeQL, mobile, iOS, resilience, and scanner workflows pass.
6. A new Comprehensive report no longer marks required scanner evidence incomplete.
