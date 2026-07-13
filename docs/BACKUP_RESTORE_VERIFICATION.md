# Backup and restore verification

## Scope

NICO records bounded evidence that an external backup completed and that a reviewed restore drill succeeded in an isolated non-production target. NICO does not create backups, download archives, connect to backup storage, execute restores, fail over a database, roll back a deployment, or mutate production data through these routes.

The control is intentionally evidence-bound. Provider documentation, plan descriptions, dashboard screenshots, and statements that backups are supported are not proof that a current backup exists or that a restore has been tested.

## Operator routes

- `GET /operations/backup-restore`
- `POST /operations/backup-restore/backup-evidence`
- `POST /operations/backup-restore/restore-drill`

All routes require the NICO admin token. The frontend keeps the token only in live React memory.

## Evidence that may be recorded

### Backup evidence

A backup record contains only:

- completion timestamp;
- bounded provider label;
- SHA-256 of a safe external backup reference;
- success state;
- encryption-at-rest verification;
- provider-separated or offsite-copy verification;
- retention period;
- point-in-time-recovery applicability and window;
- reviewer identity;
- SHA-256 and length of the reviewer note;
- active storage-schema contract identity;
- deterministic evidence SHA-256.

The raw note is not retained. Backup URLs, archive contents, database URLs, credentials, provider response bodies, access tokens, and connection strings are not accepted as evidence fields.

### Restore-drill evidence

A restore-drill record contains only:

- completion timestamp;
- bounded provider label;
- SHA-256 of the source backup reference;
- SHA-256 of a safe restored-record-set identity;
- restore success state;
- isolated non-production target verification;
- active storage-schema contract identity;
- required-table verification;
- application read verification;
- reviewer identity;
- SHA-256 and length of the reviewer note;
- deterministic evidence SHA-256.

A restore drill must never target the live production database. NICO does not execute the restore.

## Default freshness requirements

- Maximum backup evidence age: 36 hours.
- Maximum isolated restore-drill evidence age: 30 days.
- Minimum retention: 7 days.
- Minimum point-in-time-recovery window when applicable: 24 hours.

The bounded environment variables are:

- `NICO_BACKUP_MAX_AGE_HOURS`
- `NICO_RESTORE_DRILL_MAX_AGE_DAYS`
- `NICO_BACKUP_MIN_RETENTION_DAYS`
- `NICO_BACKUP_MIN_PITR_HOURS`

## Status rules

The control remains blocked when durable Postgres is unavailable, evidence is missing, evidence is stale, the latest operation failed, encryption or separated-copy verification is absent, retention or PITR is insufficient, restore isolation is unverified, required tables or application reads were not verified, the restore source does not match the latest backup reference, or the schema contract differs from the active contract.

PITR marked not applicable produces a warning rather than a verified-green claim.

The operations readiness integration is advisory. Missing backup or restore evidence degrades semantic readiness; it does not claim that core Postgres is down. Durable Postgres itself remains governed by required storage readiness checks.

## Runbook

1. Confirm the production database provider completed a real backup.
2. Independently verify completion time, encryption at rest, separated/offsite copy, retention, and PITR window.
3. Derive a safe SHA-256 reference that does not expose a URL, credential, archive name containing secrets, or provider response body.
4. Record the backup evidence through `/operations/backup-restore`.
5. Restore that exact backup into an isolated non-production target using the provider's approved operational process outside NICO.
6. Verify the target is isolated from production writes and client traffic.
7. Verify the current NICO storage-schema contract and required tables.
8. Perform bounded application reads against the isolated target.
9. Derive a safe restored-record-set SHA-256 without retaining record contents.
10. Record the restore-drill evidence.
11. Review semantic readiness and the backup/restore blockers.

## Prohibited actions

- Do not paste `DATABASE_URL`, credentials, tokens, provider URLs, archive contents, raw SQL errors, or provider payloads.
- Do not restore into production as a drill.
- Do not represent a configured backup feature as a completed backup.
- Do not represent a successful backup as proof that restoration works.
- Do not use these records to authorize client delivery, score changes, deployment, rollback, or failover.

## Deployment truth

Deploying this module does not establish backup protection. After deployment, the control must remain degraded or blocked until a real reviewed backup record and a successful isolated restore-drill record are entered. No provider backup or restore operation is claimed by this implementation.
