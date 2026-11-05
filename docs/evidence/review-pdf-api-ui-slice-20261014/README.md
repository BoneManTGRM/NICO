# Dormant retained-review PDF API and UI

Base `cd912a881eac958bf9d5d5640f88928f102cb293`, isolated branch
`fix/review-pdf-preparation`. This slice is source-only and disabled by default.
No push, workflow trigger, deployment, production access/settings, schema
initialization, installation or paid activity. C++ remains paused; the separate
database pilot remains HOLD. No private input is included.

## Behavior

Authenticated pending-review controls explicitly enqueue preparation. Status and
retrieval require the exact job/run/locale/commit/canonical truth; tenant,
project, repository, source revision/integrity and renderer/policy come from the
authoritative retained record. Existing operator/session authorizers apply;
production-proof scope is rejected. The proxy retains session forwarding and
same-origin cookie mutation protection.

POST preparation is idempotent through the existing ledger and cannot start an
assessment or approve/deliver a report. Missing review commitments fail before
restoration can initialize them. Approved/deliverable source variants cannot use
this pending-draft path. Explicit cancellation fences old workers. Terminal jobs
stay terminal rather than resetting the bounded attempt/time budget.

The existing review control reports queued/preparing/verifying/ready/failed or
cancelled, with English/Spanish messages and no fabricated percentage. Only a
saved exact-binding job resumes on reload, using GET; reload never creates a new
job. Navigation cancels observation, leaving durable work resumable. Polling uses
30-second per-request and 15-minute overall observation limits; waits and request
limits are capped to remaining time, and a final validated ready response is
consumed before the next deadline check. Byte retrieval retains the 240-second
proxy and 255-second browser deadlines, MIME/header/source checks and SHA-256
verification. Neither preparation nor retrieval confers approval/delivery.

Retrieval fully restores/revalidates the retained source, locks/rechecks raw
payload and review-history commitment, compares source snapshots, policy and
stored result ownership, verifies draft headers and PDF checksum, then streams
retained bytes. The worker now persists its full-PDF validation page-count
attestation and raw source binding. Child extraction reports verifying via an
owned heartbeat; this phase alone cannot mark a result ready.

Startup requires both explicit backend enablement and real-PG qualification,
plus the canonical runtime's verified PostgreSQL durability state. It reuses
that store's exact connection factory and existing client_jobs tables; it does
not initialize schema, resolve another database URL or fall back to SQLite or
memory. Recovery scans bounded batches with lease-aware keyset pagination and
isolates malformed rows. It uses the existing publication semaphore, preserves
original lifespan state, and cleans up partial startup. The semaphore remains
process-local, so replica/process capacity must be verified before activation.

Backend switches: `NICO_ENABLE_REVIEW_PDF_PREPARATION=true` and
`NICO_REVIEW_PDF_PG_QUALIFIED=true`; frontend build switch:
`NEXT_PUBLIC_NICO_REVIEW_PDF_PREPARATION=true`. Flags are gates, not qualification
evidence. No flag was set in production. Policy identity includes exact deployed
`RAILWAY_GIT_COMMIT_SHA` plus the existing live renderer policy fingerprint.

## Verification

- Main focused Python invocation: **100 passed**, covering API/auth/source gates,
  ledger/lease/phase, worker/full synthetic Spanish rendering, mocked PostgreSQL,
  and CI-proof safety/structure. No deselections.
- Existing public internal-job namespace suite: **49 passed** separately.
- Existing session bridge/scope/transport suite: **3 passed** separately (the
  transport wrapper itself runs its 31 JavaScript checks).
- Review-download, PDF diagnostics and localized proxy JavaScript: **87 passed**.
- Session transport JavaScript: **31 passed**, separately; this repeats the
  transport wrapper's evidence and is not an additional distinct Python test.
- TypeScript `--noEmit --incremental false` and `git diff --check`: passed.
- Existing HTTPX/pypdf deprecation warnings only in the focused passing run.

Commands:

```sh
/workspace/nico-venv/bin/python -m pytest -q \
  tests/test_review_pdf_preparation_api_v1.py \
  tests/test_review_pdf_preparation_jobs_v1.py \
  tests/test_review_pdf_preparation_postgres_v1.py \
  tests/test_review_pdf_preparation_service_v1.py \
  tests/test_postgres_review_pdf_preparation_proof.py
/workspace/nico-venv/bin/python -m pytest -q tests/test_client_job_internal_namespace_boundary.py
/workspace/nico-venv/bin/python -m pytest -q \
  tests/test_specialist_review_session_bridge_v1.py \
  tests/test_specialist_session_scope_v1.py tests/test_specialist_session_transport_v1.py
node --test tests/js/review-pdf-download.test.cjs \
  tests/js/pdf-proxy-stream-diagnostics.test.cjs tests/js/localized-edition-proxy.test.cjs
node --test tests/js/specialist-session-transport.test.cjs
./apps/web/node_modules/.bin/tsc --noEmit --incremental false --project apps/web/tsconfig.json
```

Coverage truth: a combined invocation placing the namespace suite before the
session-bridge test had **1 failure / 51 passes**. The bridge test creates a
second FastAPI app after a global installer flag is set, and that installer
returns without adding its context middleware to the second app. The identical
ordering failure was reproduced in a detached base-commit worktree (**1 failure /
50 passes**, excluding the transport wrapper). This is pre-existing test/app
installation ordering behavior, not an all-suite pass. Its isolated suite passes;
no unrelated bridge source change is included here. The new API fixture installs
its test app's context middleware explicitly.

Two independent read-only reviewers confirmed the final API/worker and UI
corrections have no remaining source blockers in their reviewed scope. Findings
fixed during review: malformed/failed recovery row starvation, prepared-PDF
proxy diagnostics/classification, preservation of lifespan state, and the final
poll response/deadline boundary.

## Outstanding release evidence

- Real PostgreSQL ledger proof and full ready/source-lock/retrieval integration
  have not run. The prepared CI proof covers ledger ownership only.
- Confirm actual canonical production adapter, same database/table access,
  restart/reclaim persistence and single bounded process/replica capacity.
- Exercise the real retained source through prepare, capture, full child render,
  finalization and retrieval. In particular, measure full source restoration and
  transaction times against the existing 30-second lease and 900-second budget;
  synchronous source restoration is not covered by child-render heartbeats.
  Do not lengthen deadlines or skip validation to obtain a pass.
- Parent-owned deployed English/Spanish desktop/mobile acceptance, failed/slow
  response recovery and unchanged scores/findings/evidence/approval/delivery.
- The attachment is absent from this executor; its recorded transfer failed.
  This slice neither rehashes the private ZIP nor reruns the private 68 MB report.
  Prior parent-owned actual retained-render evidence remains separate. Synthetic
  full-builder byte parity is not a substitute for that release test.

Read-only live refs checked successfully using git ls-remote:
main `568d5c530b9a7ecdd892d8b7f5023ba5d348e0d9`;
PR1729 branch `fix/ordinary-release-verification`
`a5a552fcb78ff6311346dd8d3154663bad7cbcb5`.
No remote `fix/review-pdf-preparation` ref was returned. Publication remains with
the parent; this slice does not declare production readiness.
