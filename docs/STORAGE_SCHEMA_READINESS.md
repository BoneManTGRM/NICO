# NICO Storage Schema Readiness

## Purpose

Hosted NICO depends on durable Postgres records for assessments, scanners, evidence, reports, approvals, operational events, and delivery workflows. A configured `DATABASE_URL` or successful TCP connection does not prove that the required tables and columns exist or that the running code and database agree on the current storage contract.

The storage-schema readiness control verifies both the live Postgres catalog and a versioned migration ledger. Missing tables, missing columns, memory fallback, query failure, or a migration-contract mismatch blocks semantic production readiness.

This control does not validate the contents of individual workflow records and does not authorize client delivery.

## Contract

The current contract is identified by:

- schema: `nico.storage_schema_readiness.v1`
- contract version: `2026.07.13.1`
- deterministic contract SHA-256

The contract enumerates every required base storage table and required column, including the `nico_schema_migrations` ledger.

The migration ledger stores:

- contract version;
- contract SHA-256;
- initial application timestamp;
- latest verification timestamp.

No database URL, credential, SQL error message, row payload, customer value, or provider response is returned by the readiness endpoint.

## Startup behavior

The production application verifies storage schema state while installing production routes.

For Postgres, NICO:

1. Creates the migration-ledger table if it does not exist.
2. Records or refreshes the current contract version and hash.
3. Reads `information_schema.columns` for the active schema.
4. Compares the observed catalog to the version-controlled expected table and column set.
5. Reads the bounded migration ledger.
6. Marks the control ready only when the catalog is complete and the current ledger row matches the exact contract hash.

For memory fallback, the application remains reachable for diagnostics but schema readiness is blocked. Memory fallback is never represented as durable or restart-safe.

A database exception is reduced to a safe exception class. Raw database messages are not retained in the readiness response.

## Operator endpoint

Use the admin-authenticated endpoint:

```text
GET /operations/storage-schema
```

Add `?refresh=true` to perform a fresh catalog and migration-ledger verification.

The endpoint returns:

- adapter and persistence state;
- contract version and SHA-256;
- expected and observed table counts;
- exact missing-table names;
- exact missing-column names;
- current migration version/hash state;
- blocker IDs;
- safe next action.

The endpoint requires `X-NICO-Admin-Token` and does not expose credentials or record payloads.

## Readiness behavior

`/operations/readiness` includes a required `storage_schema_verified` check.

Production remains blocked when:

- durable Postgres is unavailable;
- the catalog cannot be read;
- a required table is missing;
- a required column is missing;
- the current migration version is absent;
- the recorded contract hash differs;
- schema verification fails for any other reason.

Do not bypass this check by editing readiness output, removing a required column from the version-controlled contract, or manually inserting a false migration record.

## Safe migration procedure

1. Preserve a database backup or provider snapshot before structural changes.
2. Confirm the exact running release SHA.
3. Review the expected contract and migration version in source control.
4. Apply additive, backward-compatible DDL first.
5. Avoid destructive column removal or type conversion in the same release that changes application reads.
6. Deploy the application.
7. Refresh `/operations/storage-schema` with operator authentication.
8. Confirm `/operations/readiness` is `ready`.
9. Run fresh Mid and Full acceptance workflows before resuming client delivery.
10. Retain the release manifest, migration contract hash, and readiness evidence.

## Failure and rollback

When schema readiness is blocked:

- stop trusted assessment, approval, and delivery work;
- preserve existing records;
- identify the missing table, missing column, or migration mismatch from the safe readiness response;
- apply a reviewed forward repair where possible;
- use the tracked release rollback procedure only when the application release itself is incorrect;
- never restore an older database over newer production data without an approved disaster-recovery decision;
- rerun schema verification and the complete production release gate.

A green Vercel or Railway provider check does not override a blocked storage-schema state.

## Current scope

This stage proves structural database readiness and migration identity. Subsequent durability work must still verify:

- restart and resume behavior for Mid and Full runs;
- scanner recovery;
- report and approval persistence;
- delivery grant and receipt recovery;
- idempotent duplicate prevention;
- backup and restore execution against a disposable environment.
