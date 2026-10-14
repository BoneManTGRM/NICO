# Dormant retained-review PDF worker and validation seam

Base: `9024981143e11f9be453bc676be44b0d9b539fa0` on isolated
`fix/review-pdf-preparation`. No push or activation. No private retained report
rerun, assessment, production connection, schema initialization, installation,
service/permission change or paid activity occurred. C++ remains paused and the
separate database pilot remains HOLD.

## Implemented path

The coordinator accepts the existing configured capacity object and an already
enqueued identity. It claims only after acquiring capacity; duplicate/terminal
jobs do not spawn workers. No scheduler, endpoint, UI or startup wiring exists.

`RetainedSourceAuthority` restores the exact existing run snapshot through the
original run store's full validation and controller artifact projection. Missing
review-history commitments fail closed before restoration could initialize them.
It checks tenant/project/run/target/revision/integrity, canonical truth, original
PDF digest and the caller's current renderer/policy identity. Its captured digest
also covers the raw persisted payload and independent review-history commitment.
It never invokes continuation, final-report generation or canonical run saves.

The separate worker uses the complete specialist bootstrap and existing
`build_same_run_locale_pdf_response` on the retained status. No evidence or
findings are removed, no new abbreviated renderer is introduced. Private 0600
JSON files carry input/output in a temporary directory. The child owns a process
group; cancellation, failed heartbeat or wall deadline triggers the existing
termination/descendant cleanup. Heartbeats occur while rendering and parsing.
The job has its existing absolute budget and the worker receives at most 900
seconds. Failed physical-exit confirmation quarantines capacity.

The renderer child has database aliases/PG variables removed, PostgreSQL and
SQLite disabled, and database/socket-creation connection guards. The child-only
`NICO_REQUIRE_DURABLE_ASSESSMENT_STORAGE=false` permits the inert full app import
without a database; no app lifespan/routes are invoked. It is not an assessment
runtime and has no storage authority. Parent production storage requirements are
unchanged. A fresh-process regression checks zero connection attempts, including
attempts swallowed during bootstrap.

Strict PDF parsing and extraction of every page occur inside the bounded child.
The parent checks bounded bytes, exact job identity, language/truth/run/target
headers, PDF and artifact SHA-256, and child validation attestation. Then it
restores the authoritative source again. Within the ledger transaction it locks
both canonical run and review-history commitment rows (PostgreSQL `FOR SHARE`),
compares their exact captured payload/commitment fingerprint and metadata,
rechecks policy and lease/expiry/cancellation, and stores bytes/digest/owner with
`ready` in one write. SQLite's existing write transaction provides its local
serialization. This does not mutate source, approval or delivery records.

`ready` means this pending-review artifact was prepared and validated; it grants
no client-delivery authority. Output headers must remain pending human approval,
delivery blocked, and no assessment rerun. Approved/final source variants whose
existing builder returns different lifecycle headers are rejected by this seam;
existing approved-edition delivery paths must retain their own controls. Result
ownership is immutable after ready because later claims/publications are fenced.
Future retrieval must authenticate and recheck current source/policy and checksum.

## Verification and review

Focused run:

```sh
/workspace/nico-venv/bin/python -m pytest -q \
  tests/test_review_pdf_preparation_service_v1.py \
  tests/test_postgres_review_pdf_preparation_proof.py \
  tests/test_review_pdf_preparation_jobs_v1.py \
  tests/test_review_pdf_preparation_postgres_v1.py \
  tests/test_client_job_internal_namespace_boundary.py
```

**118 passed**. After adding a deterministic wall-deadline regression, that test
also passed: **119 distinct passing tests**, not one 119-test invocation. The
service suite now contains 30 tests, proof safety/structure 6, SQLite ledger 27,
PostgreSQL mock ledger 7 and public namespace 49. Existing HTTPX and pypdf
replacement deprecation warnings only. Python compilation and diff checks passed.

Coverage includes success/atomic visibility, duplicates, capacity exhaustion,
builder error, malformed PDF, checksum/identity/approval mismatch, source change,
exact payload/commitment changes, expired/reclaimed worker, cancellation,
mutation detection, policy change, missing review commitment, cleanup failures,
wall deadline, and retained approval/delivery restrictions. Source/SQL seam tests
use mocks and SQLite, not real PostgreSQL.

A real isolated Python child rendered the complete Spanish output from an
existing nonsensitive synthetic fixture. Its PDF SHA-256 exactly matched the
existing direct locale builder for the same input. Input remained unchanged.
This is synthetic byte/content parity, not the private 68 MB report or deployed
performance/acceptance evidence.

Independent reviewers found and verified repairs for the final-transaction
payload/commitment race, unbounded parent PDF parsing, cleanup-exception capacity
release, unsafe proof URI overrides and connection-attempt test observability.
Both reported no remaining blocker for this dormant local slice.

## Real PostgreSQL proof prepared, not executed

The existing `postgres-restart-proof.yml` still uses its existing
`postgres:16-alpine` service, permissions and original proofs. One additive step
runs `postgres_review_pdf_preparation_proof.py` against the already initialized
`client_jobs` schema. The script does not construct a schema-initializing adapter.
It permits only the exact loopback CI target and rejects URI query/fragment
redirects; inherited general database variables are removed before NICO imports.
All fixtures use a unique synthetic tenant/job namespace.

The proof exercises concurrent enqueue, four independent claim processes,
heartbeat/exclusion, fixture-only lease expiry/reclaim, stale heartbeat/failure/
result rejection, reconnect persistence and blocked delivery. Bounded evidence
records actual git HEAD; existing sanitizer assertions remain and the new
artifact is uploaded alongside prior evidence. No workflow has been triggered.
This proof qualifies ledger ownership only, not full worker/source-transaction
publication. That additional real-database integration remains outstanding.

## Remaining activation gates

- Execute/review real PostgreSQL tests, including the ready/source-lock transaction.
- Confirm active production adapter, existing table access and same-database binding.
- Bind authoritative renderer/policy identity and existing capacity at runtime;
  the current capacity limit is process-local, not a fleet-wide quota.
- Add authenticated preparation/status/verified retrieval and bilingual UI with
  explicit pending/failed states, plus restart scheduling and recovery integration.
- Preserve approved-edition paths; this worker seam is for pending review PDFs.
- Complete private same-input and deployed bilingual/mobile acceptance through
  the parent-owned flow. No release-readiness claim follows from this slice.
