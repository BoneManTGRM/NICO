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
NOT real-PostgreSQL concurrency/durability acceptance. No CI workflow was changed
or dispatched. No production or external database was contacted.

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

Real PostgreSQL proof additions belong in the existing isolated CI only after
review. No activation, credentials/security changes, installations, purchases,
production mutations, new assessments or approved-source expansion occurred.
C++ remains paused; the unrelated database pilot remains HOLD.
