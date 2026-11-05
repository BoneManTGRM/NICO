# One-artifact capacity qualification prototype — OFF, not public shipping policy

Base: `33b1db3a61696ac6b8eb3326f9373bb8ee3629a4` (corrected pending-source
artifact policy). The PR1776 branch is not modified by this separate work.

This module has **no runtime import, environment switch, API activation or schema
initialization**. Only explicit construction of QualificationOnlySQLiteJobs or
QualificationOnlyPostgresJobs opts into the prototype. The existing API still
constructs the original PostgresReviewPdfPreparationJobs. Ordinary behavior and
all existing authentication/source/approval/delivery gates remain unchanged.

## Qualification contract

- At most one identifiable review-PDF queue identity is retained in the store.
  Namespace-prefixed rows and legacy workflow rows count regardless of status,
  including failed/cancelled/unknown states. Exact existing identity reads remain
  idempotent. Old rows are neither upgraded nor removed.
- The sole identity reserves the entire fixed **66 MiB logical JSON payload**
  allowance. Each write checks the whole payload encoded with Python JSON,
  sorted keys, ASCII escaping, no nonfinite numbers. This is not a bound on
  database pages, TOAST/WAL/backups, duplicate reads or runtime memory.
- PostgreSQL writers take one stable global transaction advisory lock before the
  identity lock. SQLite fixtures use BEGIN IMMEDIATE. Admission and publication
  reject overflow atomically. No deletion, TTL eviction, replacement or cleanup
  of retained artifacts is provided.
- At most one execution attempt is allowed for that identity. Expired leases do
  not permit automatic reclaim, even if the old interpreter appears dead.
  Existing lease/deadline/status fences still govern publication and heartbeat.
- A separate durable occupancy marker and owner token survive cancellation,
  failure and lease expiry. Only the coordinator's physically completed child,
  stopped supervisor, idle guarded calls and confirmed private-file cleanup can
  acknowledge release. The acknowledgement changes occupancy metadata only,
  never approval, source/history, retained PDF bytes or lifecycle/lease authority.
- Failed/uncertain cleanup acknowledgement quarantines local capacity. No automatic
  retry claims that an old worker died. A released marker still does not permit
  another attempt or another retained identity.

## Evidence

Thirty focused cases passed, including independent interpreter admission/claim
races, duplicate admission, fresh-reader retention, exact 66 MiB and overflow
boundaries, legacy/terminal/malformed row accounting, lost admission acknowledgement,
expired-owner non-reclaim, cancellation fencing, pending-call/file/child/supervisor
cleanup controls, owner/transition tampering, oversized-publication rollback,
PostgreSQL lock-order/failure mocks and an actual isolated Spanish render preserving
source/history. SQLite state is disposable synthetic fixture storage only.

Final verification: **306 Python cases in 13 fresh-process suites passed**, with
zero failures/errors/skips in the final JUnit results. The retained-download case
also runs its browser/proxy regressions. One initial worktree dependency-link
failure was corrected by reusing already-installed TypeScript, without installing
packages; the failure and successful rerun are retained. Complete results and
commands are in the external handoff. PostgreSQL mock SQL checks are
NOT real-PostgreSQL concurrency/durability acceptance. The initial prototype did not change or dispatch CI. The later explicit
synthetic proof wiring is described below; no workflow was manually dispatched. No production or external database was contacted.

## Remaining decisions and limitations

This intentionally permits one retained artifact identity, not a general product.
Once full, it stays full. There is no destructive reset or administrative recovery
route. An ambiguous owner death may leave occupancy held indefinitely. Choosing
an operational reconciliation policy requires separate review and evidence.

Existing stores already above the count/byte bounds are not repaired or erased;
new work is blocked while exact-identity reads remain possible. Inventory and
starting-state qualification are still required.

All writers must cooperate with the lock protocol. Mixed old/new writers, rolling
release overlap, database topology and real PostgreSQL transaction behavior remain
unqualified. Existing ordinary queue limits are NOT changed by this prototype.

A metadata update can be rejected at the serialization ceiling; fail-closed
quarantine is preferred to exceeding the reservation. Real output-size headroom
and safe operational limits still need measurement. Qualified job capacity does
not bound concurrent source qualification/restoration or retained-PDF retrieval,
canonical final-report jobs, physical database storage or process memory.
Production-size input, 20s admission/230s retrieval/900s job budgets and resource
contention remain unqualified. The protocol scans existing client_jobs without
new indexes; a timeout fails closed.

Real PostgreSQL proof execution belongs in the existing isolated CI after review. No activation, credentials/security changes, installations, purchases,
production mutations, new assessments or approved-source expansion occurred.
C++ remains paused; the unrelated database pilot remains HOLD.


## Explicit synthetic PostgreSQL capacity proof

The proof requires `--synthetic-ci-proof`, the existing Postgres Restart Proof
GitHub Actions context, valid run identity, and the exact public loopback CI
fixture URL. It accepts all existing workflow events: pull_request, push and
workflow_dispatch. No workflow was manually dispatched.

PR 1777's first actual PostgreSQL run, 39096244641 (job 117583188723), failed
before any capacity checks completed. Parent retrieved artifact 12124548625 and
verified ZIP SHA-256
`0878ea2ede16ab66fedf5f06005007b17b93a4e3d5a5ba8e1af0f52d04a1a204`.
Its retained JSON identifies ProgrammingError in
`existing_empty_queue_and_global_first_contention`. The real psycopg parameter
parser reproduces the cause without a connection: a literal percent sign in the
namespace LIKE expression is parsed as an invalid placeholder when parameters
are supplied. The fix binds the LIKE pattern as a parameter; namespace selection,
locks, bounds and acceptance semantics do not change. A regression test uses the
actual psycopg parser/adaptor. The initial test scaffold mistakenly supplied a
Mock where PostgresAdapter was required; that setup failure is retained separately
from the subsequent intended ProgrammingError reproduction.

The same proof script retains all 14 original negative/concurrency checks and
adds 11 mandatory positive lifecycle checks. The existing workflow requires the
exact combined check set and successful_ready_publication_proven=true, using the
same service definition, step and uploaded artifact. It runs before other
review-PDF proofs populate the ordinary queue namespace. Its recorded git HEAD
must match the other proofs. A branch push alone does not run this workflow;
automatic PR CI does. PR checkout may use a merge SHA.

Negative scenarios retain their original namespace and cancelled/held reservation.
For the positive scenario, only after explicit CI/target guards pass, the proof
creates a uniquely named capacity_positive_<uuid> schema in the SAME ephemeral
CI PostgreSQL service. It clones the five required fixture tables from existing
public tables, without copying rows. No service, database, matrix lane, deletion,
reset or drop is added. Every positive ledger and source-store connection pins
search_path to that schema and pg_catalog, with no public fallback. Actual
production ledger queries and advisory-lock semantics remain unchanged. The
existing CI lifecycle disposes of the ephemeral service.

The positive path reuses build_owned_record, the real independent history
commitment/store, source restoration, actual rendering child, locked ready
publication, and complete retrieval validators from the existing lifecycle proof.
A pass-through observer asserts occupancy remains held while the child runs and
through actual private-file cleanup. At the real cleanup receipt it requires
confirmed physical exit, cleaned files, idle guards and a stopped supervisor.
Calling the unmodified receipt must change only execution_state and update time:
reservation, identity, result bytes and status remain retained. No validation is
stubbed, ready row manufactured, or cleanup state invented.

After ready publication, the proof verifies the unchanged 64 MiB encoded-result
limit and 66 MiB logical JSON limit, duplicate idempotency and no second claim.
A distinct identity must still fail specifically with
qualification_one_artifact_full. The original PDF remains retrievable through
the real runtime after that rejection. A fresh interpreter uses the same pinned
schema and qualification ledger to verify digest, length, source identity and
pending-review/delivery gates. Source record and independent history commitment
must remain unchanged. All rollout flags remain false; constructor selection is
proof-only. Failure retains phase, completed checks, safe repository code location
and exception class, without SQL values, exception text or secrets.

Local tests use the actual psycopg parser and a real SQLite source/renderer to
exercise the positive observers and unchanged result validator. They also check
schema guards, pinned connection options, supported events and workflow/evidence
wiring. SQLite is not PostgreSQL concurrency or fresh-process PG retrieval proof.
Actual execution of the corrected combined proof remains pending automatic PR CI;
no success is claimed from the local harness. Production-size timing and resource
qualification also remain open. C++ remains paused; database pilot remains HOLD.

Fresh local validation of the correction (all exit 0; 91 passed total):

```text
/workspace/nico-venv/bin/pytest -q tests/test_postgres_review_pdf_capacity_proof.py
46 passed, 3 warnings in 5.74s
/workspace/nico-venv/bin/pytest -q tests/test_review_pdf_single_artifact_qualification.py
31 passed, 3 warnings in 13.91s
/workspace/nico-venv/bin/pytest -q tests/test_postgres_review_pdf_preparation_proof.py tests/test_review_pdf_real_source_lifecycle.py
14 passed, 6 warnings in 18.37s
```

Warnings are existing pypdf deprecations. Logs/JUnit files are retained under
`/workspace/pdf-capacity-qualification-handoff/correction-*`. Before/after event
and psycopg-parser reproductions are retained there too. The first positive local
test incorrectly attempted the PostgreSQL-only runtime lookup against SQLite;
that failure is preserved in positive-harness-initial.txt. The corrected local
test derives the real identity and validates retained bytes with the actual
validator, without stubbing runtime lookup or claiming PG retrieval. Fresh-process
runtime retrieval remains a mandatory actual-PG CI check.

Main 644b5516bf6dcace88de5178b88bffa1fb11e76e was normally merged before this
correction; no force push, deployment or activation is part of this work.
