# Read-only PDF storage compatibility diagnostic

Base: 2857c2355c27930954fbff95d9897a2494f41a60. This diagnostic does not
activate durable PDF preparation, change storage, or fix rendering time.

An authenticated GET on the existing route
`/assessment/comprehensive-run/{run_id}/review-pdf/{en|es-MX}?storage_compatibility=true`
returns only closed compatibility fields. The frontend's existing `/api/nico/assessment/...`
proxy preserves the query and its 30-second read deadline. The run identifier and
language must be syntactically valid; this is storage-wide metadata, not a report
lookup or assertion that the named run exists. No customer records are accessed.

Existing specialist/operator authorization remains mandatory; proof-scoped sessions
are rejected. Duplicate/extra parameters, PDF suffix and POST diagnostic requests
are rejected. The read works independently of dormant PDF activation flags and never
calls preparation, restoration, recovery, schema initialization or migration.

It uses the already-running canonical store's fresh connection factory. Its
transaction is READ ONLY, with 3-second statement, 1-second lock and 5-second idle
transaction limits. A 10-second caller deadline and single execution slot bound
admission; timed-out work retains the slot until physical completion and cleanup.
No automatic retry occurs. Late connections close before catalog queries begin.
Rollback and close apply to acquired fresh idle connections. Unexpected non-idle
connections are closed without diagnostic SQL or an explicit rollback call.

The three catalog checks cover ordinary/partitioned tables, SELECT permission and
required column names in client_jobs, nico_comprehensive_runs and
nico_comprehensive_review_history_commitments. No application table rows are read.
All raw errors, connection strings, schema names and provider objects are omitted.
Missing/malformed runtime evidence is null, not false; observed absence is false.
`probe_complete=false`, busy or unavailable must never be treated as compatible.
A successful result establishes catalog-read compatibility only. It does not prove
column types, unique constraints, write capability, durable job lifecycle,
independent restart survival, or large-report admission performance. The durability
field is explicitly the running application's claim. `lifecycle_qualified` is
always false.

## Local validation

Python 3.12:
```
python -m pytest -q tests/test_review_pdf_storage_diagnostic_v1.py tests/test_review_pdf_preparation_api_v1.py tests/test_review_pdf_preparation_service_v1.py
```
96 passed, 8 existing dependency/deprecation warnings. The suite includes existing
isolated synthetic EN/es-MX worker rendering, authentication, source binding and
artifact validation; it does not contact production PostgreSQL.

```
node --test tests/js/pdf-proxy-stream-diagnostics.test.cjs
```
14 passed, including actual proxy query forwarding and unchanged 30-second deadline.
`git diff --check` passed. An earlier command named a nonexistent deadline test file
and collected no tests; final figures above are from the corrected complete run.
A new JS assertion initially treated a URL object as a string; corrected conversion
preserves the exact URL assertion. Independent review found and verified fixes for
unknown-value collapse and connection cleanup. No remaining source-review blocker.

## Proposed deployment and observation, not executed

1. Parent approves publication/review of this diagnostic-only patch, then normal
   exact-head hosted CI/security checks and merge/deployment under existing controls.
2. Keep all PDF preparation activation flags unchanged. No schema/configuration or
   credential changes; ordinary deployment only after separate approval.
3. Through the existing authorized operator session, make one GET with the explicit
   diagnostic query and retain only its bounded JSON. Do not import startup code in
   a shell or use a recovery diagnostic endpoint.
4. If incomplete/incompatible, stop qualification and diagnose only the reported
   missing prerequisite. If catalog-compatible, proceed only with the separately
   approved isolated lifecycle and large-source qualification; no activation implied.

Rollback is ordinary code revert/redeploy; no data migration or record rollback is
needed. Current main, original assessment/report artifacts, scoring, review and
client-delivery gates remain unchanged. No publication or deployment performed.
