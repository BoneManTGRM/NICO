# NICO Comprehensive Production Runbook

This runbook supplements detailed documents under `docs/`. It defines the minimum operating boundary for **NICO Comprehensive Technical Assessment**.

## Release procedure

1. Confirm the branch is based on the current `main` commit.
2. Record pre-existing failures before changing code.
3. Define observable success, failure, permission, missing-data, retry, timeout, audit, API, UI, migration, and rollback acceptance criteria.
4. Implement one coherent release-quality change.
5. Run all applicable formatting, type, unit, integration, contract, API, migration, end-to-end, build, security, dependency, secret, scanner, report, accessibility, performance, and recovery checks.
6. Review the complete diff for authorization, tenant isolation, injection, insecure defaults, races, partial writes, frontend/backend drift, unbounded work, sensitive logging, evidence assumptions, unsupported certainty, migration risk, and untested paths.
7. Open a pull request documenting root cause, solution, user effect, security effect, data effect, tests, migration, rollback, limitations, and residual risk.
8. Do not merge with failed, pending, cancelled, inconclusive, unexpectedly skipped, flaky, stale-commit, or wrong-commit required checks.
9. After merge, verify default-branch CI, exact frontend/backend deployment identity, application startup, migrations, production readiness, and affected workflows.
10. For release-sensitive changes, retain two consecutive live Comprehensive passes on the exact deployed commit.

## Rollback

- Prefer a code revert when no migration changed stored data.
- Before migration rollback, verify whether the prior application can read the current schema.
- Never perform destructive rollback on production data without explicit approval and a verified backup.
- Record release SHA, rollback SHA, database identity, migration version, operator, timestamp, reason, and verification evidence.
- Re-run readiness and exact-release smoke checks after rollback.

## Scanner failure

1. Preserve requested tool, version, configuration, immutable commit, invocation, exit status, runtime, bounded redacted output, and artifact checksum.
2. Classify the result as unavailable, failed, timed out, malformed, partial, or unsupported.
3. Do not grant completion credit.
4. Retry only within configured bounded policy.
5. Prevent duplicate jobs and findings through idempotency keys.
6. Escalate required-tool failure and block dependent completion.
7. Permit optional-tool continuation only when the limitation is explicit and dependent conclusions remain defensible.

## Workflow and queue recovery

1. Locate the exact assessment, run, repository snapshot, stage, and job identity.
2. Confirm durable persisted state before retry.
3. Reconcile stale queued or running records using bounded timeout rules.
4. Resume the same run and stage when safe; do not create a replacement run to hide failure.
5. Use idempotency keys to prevent duplicate evidence, findings, reports, and notifications.
6. Route unrecoverable work to a failed-job or recovery queue with a client-safe status and operator diagnostics.
7. Verify successful continuation from the exact checkpoint.

## Report-generation failure

1. Preserve canonical assessment data and generation diagnostics.
2. Identify whether the failure affects Markdown, HTML, JSON, PDF, presentation, or all formats.
3. Do not expose review or delivery actions when required artifacts or invariants fail.
4. Regenerate from canonical data rather than manually editing an artifact.
5. Run cross-format identity, score, severity, count, finality, approval, roadmap, and evidence checks.
6. Require zero failed deliverable invariants before review can proceed.

## Production backup, restore, and recovery

1. Confirm the active production database identity and exact application SHA.
2. Create an encrypted backup without credentials in command arguments, logs, diagnostics, or artifacts.
3. Record timestamp, digest, encryption posture, schema version, and source identity.
4. Restore into an isolated non-production target.
5. Compare schema, tables, row counts, bounded record fingerprints, critical run/report/approval/queue records, and tenant identities.
6. Measure recovery time.
7. Exercise application rollback against the approved restore target.
8. Retain redacted evidence.
9. Do not describe CI restart tests as a completed production restore drill.

## Security incident

1. Stop affected processing without destroying evidence.
2. Preserve correlation IDs, audit history, release identity, tenant, run, access decisions, and bounded redacted logs.
3. Revoke exposed sessions, tokens, or delivery grants through approved procedures.
4. Rotate secrets only with explicit authorization and confirm dependent services recover.
5. Assess cross-tenant exposure.
6. Record scope, timeline, containment, eradication, recovery, residual risk, and notification decisions.
7. Do not place sensitive evidence in public issues or pull requests.

## Client-data deletion

1. Require verified tenant, engagement, legal authority, retention policy, and approval.
2. Enumerate primary data, evidence artifacts, reports, delivery grants, receipts, backups, indexes, and derived records.
3. Generate a deletion plan before execution.
4. Perform deletion through audited bounded operations.
5. Verify inaccessible and deleted states without exposing content.
6. Record backup-retention exceptions and expiration dates.
7. Never delete data automatically because an assessment or contract ended.

## Human approval boundaries

Explicit approval is required before merging or deploying changes involving authentication, authorization, cryptography, secrets, tenant isolation, destructive migrations, production infrastructure, billing, legal or compliance claims, production client code, material data deletion, risk acceptance, or unclear rollback.

When a protected item is awaiting approval, continue only with independent low-risk work.
