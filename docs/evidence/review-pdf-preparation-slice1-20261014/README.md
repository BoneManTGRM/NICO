# Ordinary review-PDF preparation: dormant durable-ledger slice

Base: `a5a552fcb78ff6311346dd8d3154663bad7cbcb5`. Separate branch excludes both
performance candidates. The owner explicitly authorized isolated implementation
and tests on October 14; production changes, spending and deployment remain out
of scope. This slice does not fix deployed download behavior by itself.

## Storage finding

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
