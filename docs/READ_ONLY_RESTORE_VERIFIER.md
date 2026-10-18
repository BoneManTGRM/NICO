# Bounded read-only restore observation

`python scripts/verify_restored_storage_readonly.py --service <existing_profile>` observes an already restored Postgres target. It does not restore a backup, initialize schema, migrate storage, record operational evidence, or establish restore provenance. No NICO application bootstrap is imported. The current contract and pure comparison functions are shared with storage readiness through `nico/storage_schema_contract_v1.py`; their definitions and contract hash are unchanged.

## Before any real execution

An authorized operator must independently establish and retain:

1. The provider's successful backup receipt: immutable backup identifier, actual completion time, and the exact safe-reference hashing convention used for `backup_reference_sha256`. Labels supplied to a script are not proof. Encryption, separated copy, retention and PITR evidence remain separate requirements.
2. The completed restore job's provider receipt binding that exact backup reference to the actual target service and volume, restore/recovery completion time and recovery target. Reading an October 16 restore cannot prove restoration of an October 18 backup. A new observation timestamp cannot replace the restore completion timestamp.
3. Target isolation from production writes and client traffic, and a trusted existing libpq service profile for that target. Have the platform/operator provision and validate access independently; do not paste URLs/passwords into arguments, output, tickets or evidence records. Use a role without write/DDL/TEMP privileges. The service/profile name alone proves neither isolation nor provenance.
4. The exact reviewed verifier source, installed Python/psycopg 3 and the current storage contract. Execute from an existing authorized host that can reach the isolated target. Do not create infrastructure, install credentials, change networking or point the verifier at production to make it work.

Only after these prerequisites and execution authorization exist:

```sh
timeout --kill-after=5s 90s python scripts/verify_restored_storage_readonly.py \
  --service isolated_restore --schema public --sample-rows 3
```

`isolated_restore` is an example existing profile name, not a profile created by this change. An external wall-clock watchdog is required; server statement timeouts do not bound a lost network connection. The verifier accepts no backup labels/provenance flags and does not read/display profile credentials itself. libpq uses the existing operator-managed profile. No execution against a real database was performed during development.

## Read behavior and bounds

The CLI sets `default_transaction_read_only=on` at connection startup, uses a five-second connect timeout, then explicitly starts `REPEATABLE READ READ ONLY`. It checks both transaction properties before data queries, qualifies target relations, limits `search_path` to `pg_catalog`, sets three-second statement and one-second lock timeouts, and always attempts `ROLLBACK`. It closes its connection. A programmatic caller must supply an idle connection exclusively owned by the attempt; existing transactions are refused without rollback.

The verifier checks the requested schema, all required columns of the existing 14-table contract, and the already-present current migration-ledger row/hash. It never calls the readiness function that updates that ledger or constructs a schema-initializing storage adapter.

There are at most 256 catalog rows and 25 sampled rows per non-ledger table (default three). Every transferred field is SQL-truncated to 257 characters and rejected above 256 characters/1024 UTF-8 bytes. Sample order is each table's existing primary identifier. Payload bodies and scanner blobs are not returned: for JSONB application payloads only the object type is checked. At least one sampled row in each of `assessment_runs` and `reports` is required; empty application samples block rather than claim a data-read check. Per-statement timeouts bound SQL execution; the external watchdog bounds total execution. No hard server-memory qualification is claimed.

The observation contains only the contract hash, fixed table/field names, sample counts, per-table hashes and one combined `record_set_sha256`. It does not emit identifiers, payload contents, credentials or raw database errors. The digest covers the selected identifier/status/payload-type projections and their sampling parameters. It is **not a full-database checksum, payload-integrity validation, report replay, or proof that all records match the backup**. Changes outside the selected projections/samples may not affect it.

## Meaning and evidence boundaries

A successful result has `status=verified_read_observation`, `required_tables_verified=true`, `migration_contract_verified=true`, and `bounded_application_reads_verified=true`. It always has `restore_provenance_verified=false` and `evidence_record_written=false`. The narrower application-read field is intentional: an operator must decide whether these projections meet the separately agreed restore drill's application-read requirement; the tool does not automatically set the existing evidence API's `application_read_verified` field.

Missing schema/table/column, missing or mismatched migration contract, unsuccessful/incompatible reads, empty application samples, bounds violations, failed read-only establishment or failed rollback produce `status=blocked`, no record-set digest and no table sample export. Earlier completed checks may be listed independently; only the overall status determines successful observation.

After reviewing genuine provenance and successful read observations, a separately authorized operator may record evidence through the existing backup/restore routes. Use the exact backup-reference hash for both backup and restore evidence and preserve actual operation timestamps. This script makes no evidence API requests and cannot satisfy the backup gate by itself. Existing freshness, encryption, retention, PITR, schema and exact-source requirements are unchanged. C++ remains paused; database pilot remains on HOLD.

## Reviewed trust and acceptance scope

The existing release gate (`nico/backup_restore_readiness.py`) requires `application_read_verified`, and `docs/BACKUP_RESTORE_VERIFICATION.md` requires bounded application reads without specifying a table-level OR/AND policy. This verifier conservatively requires nonempty, compatible samples from both `assessment_runs` and `reports`; one cannot substitute for the other. This remains a narrower observation and does not automatically satisfy the release gate.

Read-only transactions rely on a trusted restored schema. They do not universally sandbox malicious views, row-level security policies, custom casts or other server-side code. This verifier does not independently establish relation types or uniqueness of sampling keys. Stable digest comparisons additionally rely on unique ordering keys and unchanged sampling semantics; catalog column presence alone proves neither. The operator must establish schema trust before execution.

The migration-ledger hash projection is SQL-bounded to 65 characters, so overlong hashes remain distinguishable from the exact 64-character expected hash and are rejected without transferring the full field. Parser errors use only a fixed `invalid_arguments` message, including unknown options, invalid integers and missing arguments.

## Synthetic PostgreSQL qualification

The existing `Postgres Restart Proof` CI job runs `scripts/postgres_readonly_restore_proof.py` against its already configured PostgreSQL 16 service. The proof refuses non-CI execution and any connection target other than that exact loopback synthetic fixture; inherited libpq and production connection settings are cleared. It creates and removes only a unique synthetic schema, with minimal contract-compatible tables and JSONB payloads. This is test setup, separate from the read-only verifier.

The proof checks successful and repeat reads, missing schema/table, mismatched and overlong ledger hashes, PostgreSQL rejection of an attempted write inside the verifier's actual transaction, rollback, and equality of the tested table/column names, column types and rows before and after every observation. Intentional fixture mutations occur between observations. It verifies cleanup and writes bounded CI evidence with the verifier source hash. The comparison does not cover indexes, constraints, functions, policies or every schema object. It does not claim to compare unrelated schemas, qualify the CLI's operator-managed libpq profile, or establish an actual backup restore's provenance. A passing synthetic CI execution is required before claiming real PostgreSQL qualification; local safety tests alone are insufficient.

## Separate Comprehensive metadata observation

`scripts/restore_observation/` contains a separate bounded SQL probe and standalone console wrappers for `nico_comprehensive_runs` and its bound browser projection. Comprehensive reports live in the canonical payload's final-report stage, not the generic SQL `reports` table. An empty generic table therefore does not establish Comprehensive report loss. The generic verifier above retains its original scope and acceptance behavior.

The Comprehensive probe checks all 14 original contract tables' required columns plus the 12 canonical and 6 browser-projection columns, the migration ledger, exact run identity, row/projection linkage, and stored manifest/envelope metadata. It reports a SQL-scoped observation digest. It does **not** decode compressed payloads, recompute canonical/projection/report hashes, verify review-history commitments, prove restore provenance, or register readiness evidence. Passing envelope metadata can coexist with invalid compressed bytes; the proof deliberately tests this limitation. Column presence does not prove types, constraints, or schema trust.

`observe-console.sh` requires existing nonsecret `POSTGRES_USER`, `POSTGRES_DB`, and `NICO_EXPECTED_RUN_ID`; `discover-console.sh` returns at most three terminal IDs for a separate historical-identity check. Both require the existing local socket, trusted schema and reviewed least-privilege role, libpq16+ (`require_auth=none` fails closed on older clients), no password/passfile authentication, and GNU timeout. They clear inherited environment, disable psql startup files, use read-only repeatable-read transactions and rollback, and enforce a 90-second watchdog with 5-second kill grace. A transaction-closed marker alone is not success: inspect JSON status. Errors exit nonzero. Do not expect runs created after a backup in its restored snapshot.

The existing PostgreSQL16 CI workflow runs `postgres_comprehensive_observation_proof.py`. It refuses non-CI/non-loopback targets and uses only the existing synthetic service. Setup creates a uniquely named temporary database; the unchanged wrappers run through a psql shim forwarding their arguments and PG environment to that container's libpq16/local socket. No auth configuration changes or new services occur. The proof checks compressed/uncompressed metadata, discovery, wrong store/run, row/projection binding, malformed digests/envelopes, nulls, missing columns, duplicate rows, error exit, unchanged table/column/row snapshots, session closure, and cleanup. JSON evidence binds the probe/wrapper hashes and exact CI commit. A passing workflow result is required before claiming PostgreSQL execution qualification. No production restore claim is made.
