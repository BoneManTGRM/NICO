# Sandboxed Worker Rollout Checklist

Use this checklist to move NICO from hosted-only repository inspection to worker-backed scanner evidence.

## Phase 1: Artifact foundation

- [x] Define scanner-worker artifact schema.
- [x] Normalize completed, missing, and finding-count evidence.
- [x] Keep missing tools marked unavailable.
- [x] Add tests for partial artifacts and Bandit finding counts.

## Phase 2: Worker execution

- [ ] Add isolated workspace lifecycle.
- [ ] Add authorized git checkout by repository and ref.
- [ ] Add subprocess timeout and output-size limits.
- [ ] Add redaction pass before artifact persistence.

## Phase 3: Tool runners

- [ ] Bandit runner.
- [ ] Semgrep runner.
- [ ] ESLint runner.
- [ ] TypeScript/typecheck runner.
- [ ] Gitleaks runner.
- [ ] TruffleHog runner.

## Phase 4: Hosted integration

- [ ] Store scanner-worker artifacts with the assessment.
- [ ] Attach artifact evidence to Static Analysis and Secrets Exposure Review.
- [ ] Use worker artifacts to reduce Velocity / Complexity uncertainty.
- [ ] Keep human/client acceptance separate from scanner evidence.

## Phase 5: Production safety

- [ ] Add repository/ref allowlist validation.
- [ ] Add per-run resource limits.
- [ ] Add structured audit log for worker start, finish, timeout, and failure.
- [ ] Add deployment health check.
