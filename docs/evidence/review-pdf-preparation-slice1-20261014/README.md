# Ordinary review-PDF preparation: local SQLite test scaffold

Base: `a5a552fcb78ff6311346dd8d3154663bad7cbcb5`. Separate branch excludes both
performance candidates. The owner explicitly authorized isolated implementation
and tests on October 14; production changes, spending and deployment remain out
of scope. This slice does not fix deployed download behavior by itself.

## Storage finding

**Correction after production architecture review:** this slice is a local test
scaffold, not a production-ready durable ledger. Its SQLite adapter type check
does not verify a persistent mount, and reopening a local test file does not
prove survival of container replacement or sharing between replicas.

The parent verified Railway service `d9d51992-d34a-4348-a83d-1f760faaa6a8`
through `describe_service` at 17:36 UTC on October 14, 2026: `volumes: []`, one
replica in `europe-west4-drams3a`, no staged changes, source
`568d5c530b9a7ecdd892d8b7f5023ba5d348e0d9`. `DATABASE_URL` and
`NICO_DISABLE_POSTGRES` are defined; their values were not retrieved. This
metadata does not establish which adapter is active. No new volume or database
pilot activation is authorized. Local SQLite must not be activated for this job.

### Source wiring and activation boundary

- `Dockerfile:32-35` requires durable delivery/assessment storage but enables the
  SQLite fallback at `/data/nico-runtime.sqlite3`; the path itself supplies no
  volume. `NICO_WEB_WORKERS=1` is a default, not a distributed lock.
- `nico/api/production_bootstrap.py` installs the general storage facade and
  durability truth wrappers. `nico/durable_runtime_storage.py` prefers resolved
  PostgreSQL aliases, otherwise permits explicitly enabled SQLite. The general
  facade also observes `NICO_DISABLE_POSTGRES`.
- `nico/comprehensive_production_bootstrap.py` resolves the same private database
  aliases for the canonical run store, or explicitly enabled SQLite with its
  persistence proof. With durable assessment storage required, unverified SQLite
  is blocked. Its PostgreSQL selection does not consult the general facade's
  `NICO_DISABLE_POSTGRES` flag. Therefore presence of those two variable names
  cannot prove that the general facade and canonical run store use the same DB.
- `nico/comprehensive_runtime.py` constructs `ComprehensiveRunStore` using the
  selected connection factory. Canonical runs and existing final-report lease
  rows live in `nico_comprehensive_runs` and
  `nico_comprehensive_final_report_jobs`, not the general `client_jobs` collection.
- This scaffold would instead write `nico_records` rows with
  `table_name='client_jobs'` in the supplied SQLite adapter's file. It has no
  production binding. PostgreSQL has an existing `client_jobs` JSONB table in
  `nico/storage.py`; using it could avoid new DDL, but only after confirming the
  active shared database, existing table, authorized access, and binding to the
  canonical store. Those production conditions are not established here.

`BEGIN IMMEDIATE` serializes writers on the **same SQLite file**; lease tokens
fence stale owners only within that file. Separate replica/container files do
not coordinate. The existing publication semaphore is explicitly process-local;
it is not a global worker-capacity limit. A PostgreSQL implementation would need
atomic enqueue/claim and lease-fenced writes in shared database transactions,
including concurrent-process, restart and stale-owner tests. Existing revision
checks on canonical runs do not automatically protect this separate ledger.

No new volume, schema, service or security permission is required by the dormant
scaffold. Production activation cannot proceed on it. A same-database PostgreSQL
implementation might require no infrastructure expansion, but that remains
conditional on the existing-table/access checks above; no schema creation or
permission expansion is authorized implicitly. If no suitable existing durable
store is available, stop rather than provision one. API/UI and worker activation
are paused pending this prerequisite. All results remain `rendered_unverified`
until full artifact validation and an authoritative source-binding recheck.

No new schema is needed for this slice. Existing `SQLiteRuntimeAdapter` has
`nico_records`, including the logical `client_jobs` collection. Existing
PostgreSQL has a JSONB `client_jobs` table suitable for a corresponding adapter.
This implementation supports **only the existing SQLite adapter** and rejects
memory/unsupported adapters; PostgreSQL transaction implementation and validation
remain outstanding. It constructs no adapter, initializes no schema, opens no
worker, and registers no route on import or construction. Tests use disposable
SQLite files and the existing adapter schema, never production databases.

## Implemented boundaries

- Deterministic identity binds customer, project, run, repository, assessed SHA,
  source revision, source-integrity/truth/artifact digests, renderer revision,
  policy digest and locale.
- Short `BEGIN IMMEDIATE` transactions deduplicate enqueue and serialize lease
  claims across connections. Existing assessments and report bytes are untouched.
- Thirty-second leases, a 900-second absolute job budget and at most two claims
  bound abandoned-worker recovery. Heartbeat cannot extend the absolute budget.
  Failure is terminal in this slice; no automatic failed-job retry is enabled.
- Expired/replaced leases cannot record a result. An observed source identity
  mismatch is rejected. The future coordinator must derive and verify that
  observed identity from authoritative storage; callers cannot supply authority.
- Result state is `rendered_unverified`, with a PDF digest only. No artifact
  bytes are retained yet, no ready/download state exists, and no semantic
  verification or authorization is inferred from the digest.
- Public client-job create/read/export paths reject the new internal prefix and
  workflow, including legacy IDs carrying the workflow. This narrows public
  access and grants no account or endpoint permission.

The internal enqueue flag expresses a required caller precondition; it is not
authentication. No API exposes this ledger. The eventual authenticated service
must validate source integrity/terminal status and derive all binding fields.

## Local verification

```sh
python -m pytest -q tests/test_review_pdf_preparation_jobs_v1.py
python -m pytest -q tests/test_client_job_internal_namespace_boundary.py
```

The first command covers identity dimensions, invalid identities, volatile-store
rejection, explicit enqueue authorization, concurrent enqueue/claim, reopen,
expired-worker fencing, changed source/tenant, deadline/attempt limits and
unchanged source bytes/schema. The second covers public namespace/workflow
protection, including mounted public routes and unchanged ordinary draft flows.

Results: **27 preparation tests and 49 public-boundary tests passed**. Independent
read-only verification also ran all 76 checks successfully and found no blocking
finding for the dormant SQLite-only scope. `git diff --check` passed. The test
client emitted its existing HTTPX deprecation warning; no test failed.

## Next slices, not implemented

1. Verify active durable-adapter applicability without exposing credentials;
   implement/test PostgreSQL transactions if required, using its existing table.
2. Integrate with existing bounded publication capacity and isolated rendering;
   do not repurpose canonical-stage continuation or alter approved-edition rules.
3. Authoritative source recheck, atomic verified-artifact retention, full original
   builder/validator execution, stale-result and release-policy invalidation.
4. Explicitly authenticated preparation/status/retrieval endpoints with existing
   tenant/run access checks, followed by honest bilingual preparation UI.
5. Same-input actual-report content parity and deployed delivery/recovery checks.

Do not activate this partial ledger or claim download readiness. No push, hosted
CI, migration execution, assessment, production mutation, spending, merge,
deployment or C++ work occurred. Database pilot remains HOLD.

## Follow-up storage verification

Using `/workspace/nico-venv/bin/python`, ran the hosted-persistence guard,
runtime-storage-truth and preparation-ledger suites together: **34 passed,
2 failed**. All 27 ledger tests and all 5 hosted-persistence tests passed.
Two existing runtime-storage-truth tests expected the temporary SQLite path to
be non-durable. This executor's `/tmp` is a separate `tmpfs` mount/device;
`runtime_storage_truth_patch.sqlite_mount_verified` accepts a different device
without excluding tmpfs, so it reported verified durability. The canonical
bootstrap uses a separate detector that excludes ephemeral filesystem types.
This is an additional reason not to use the general adapter's durability flag
alone as activation evidence. No repair or production conclusion is inferred
from these two failures; they are retained as an unresolved storage-truth issue.
The first invocation with system Python could not run because pytest was absent;
the existing project virtual environment supplied the reported test run.

`git diff --check` passed. This follow-up changes documentation/module labeling
only and deliberately does not advance API/UI or runtime activation. Required
next evidence is the active canonical/general adapter selection and confirmation
that the existing shared durable database contains the authorized job table;
variable values or credentials are not needed in the handoff.

## Authorized source-only PostgreSQL and mount-classification follow-up

This section supersedes the earlier statement that PostgreSQL source support is
unimplemented. Activation remains blocked. `PostgresReviewPdfPreparationJobs`
accepts an already constructed `PostgresAdapter`; it neither constructs one nor
executes its schema initializer. It writes only the existing `client_jobs`
columns, with JSONB payload and timestamp conversion. No migration, dependency
installation, service change, new volume or production database access occurred.

Each mutation takes a transaction-scoped advisory lock derived from the complete
job identity, before reading or inserting the row. This includes the absent-row
enqueue race. READ COMMITTED ensures the read after waiting sees the preceding
commit; `clock_timestamp()` checks expiry after lock acquisition, unlike a
transaction-start clock. Lock wait is bounded to five seconds; errors roll back
and close the connection. Identity, tenant, lease, attempt and deadline checks
remain in effect. The lock coordinates cooperating ledger writers in the same
database, not separate databases or global render capacity. Activation requires
confirming existing advisory-lock function access as well as table privileges;
no permission grant is implemented or authorized here.

No PostgreSQL binaries, local socket or running Docker fixture were available.
Psycopg is already installed, but no server was provisioned. The seven new tests
use a **mock driver only**: they check transaction ordering, bounded lock failure,
deduplication decisions, scope/source conflicts, lease fencing, limits, rollback
and unverified results. They do not establish real PostgreSQL concurrency,
isolation, JSONB adaptation, restart durability or SQL execution compatibility.
Those checks remain explicit gates before activation, alongside live adapter and
existing-table readiness. Parent also reports redacted connector variables and
a blocked health route; no alternate transport was attempted.

The mount defect was reproduced before repair: seven failures (the two original
tests plus five synthetic ephemeral/nested/missing-evidence cases), four passes.
The general storage detector now classifies the nearest containing mount from
mountinfo, rejecting ephemeral filesystems and ambiguous/missing mount evidence.
It no longer treats a different device or any mount point as durability proof.
Existing explicit operator confirmation is preserved. ext4/xfs cases pass;
tmpfs/ramfs/overlay, nested ephemeral mounts and missing evidence fail closed.
This correction does not establish durability for Railway's volume-less service.

Focused run after repair: **99 passed**, comprising 27 SQLite ledger tests,
7 PostgreSQL mock tests, 11 storage-truth tests, 5 hosted-persistence guard tests
and 49 public client-job boundary tests. Existing HTTPX deprecation warning only.
No runtime wiring, API/UI or artifact publication was added. All rendered results
remain `rendered_unverified`, requiring full validation and authoritative source
recheck before any future ready/download transition.

Independent review caught ambiguous stacked mounts at the same path; both entry
orders now fail closed. Those two additional regressions increase total coverage
to 101 tests (13 storage-truth tests). PostgreSQL transaction setup uses
`SET TRANSACTION ISOLATION LEVEL READ COMMITTED` after psycopg's implicit BEGIN,
avoiding a redundant explicit BEGIN. Independent PostgreSQL review found no
blocking correctness issue within the dormant mock-qualified scope. Full real
PostgreSQL concurrent deduplication/claim, process restart and fencing tests are
still not run and must not be inferred from these results.

After the final two corrections, reran the affected suites: 18 storage/hosted
checks passed, then 20 PostgreSQL-mock/storage-truth checks passed. Together with
the unchanged suites from the 99-test run this covers 101 distinct passing tests;
there was no single 101-test invocation. The mount reviewer independently
confirmed the stacked-mount finding resolved with no remaining blocker.
