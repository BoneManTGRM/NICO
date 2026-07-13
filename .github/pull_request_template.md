## Problem and evidence

Describe the defect or improvement and the evidence that supports it.

## Change

Describe the smallest safe change.

## Safety and authorization

- [ ] Defensive-only behavior is preserved.
- [ ] Explicit authorization remains required where applicable.
- [ ] No credential, token, private client data, or raw secret evidence is committed.
- [ ] Human approval and client-delivery boundaries are not weakened.

## Truth and integrity

- [ ] Missing, pending, failed, and unavailable evidence remain distinct.
- [ ] Scores or readiness states are not lifted cosmetically.
- [ ] Exact repository, customer, project, run, scan, report, approval, and artifact identities are preserved where applicable.
- [ ] Synthetic fixtures and live evidence are clearly distinguished.

## Verification

List exact commands and results.

```text
pytest ...
npm run lint
npm run build
```

- [ ] A regression test fails before the change and passes after it, or the reason tests are not applicable is documented.
- [ ] Required CI checks pass.
- [ ] Deployment checks are required before claiming production success.

## Migration and rollback

Describe state migration, compatibility, recovery, and rollback impact.

## Documentation

- [ ] Canonical documentation was updated when behavior or maturity changed.
- [ ] No redundant versioned guide was added.

## Merge gate

Do not merge with failed required checks, unresolved review threads, unexplained score changes, or unsupported production claims.
