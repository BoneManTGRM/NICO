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


## Explicit synthetic PostgreSQL capacity proof (not yet executed)

`postgres_review_pdf_capacity_proof.py` requires `--synthetic-ci-proof`, the existing
Postgres Restart Proof GitHub Actions context, a PR/push event and the exact public
loopback CI fixture URL. It rejects unsupported prerequisites before connecting.
It uses existing tables only, fails if the queue namespace is occupied, scrubs
inherited production aliases and keeps rollout flags false. No schema creation,
cleanup/deletion, new service or production configuration is included.

The existing workflow now places this step BEFORE the old review-PDF ledger proof,
which otherwise populates the globally counted namespace. The new proof retains
bounded JSON evidence (including completed checks, phase, individual synthetic
outcomes and failures) in the existing always-uploaded artifact. It requires all
14 named checks and binds its recorded git HEAD to the other proofs' source SHA.
No draft/flag skip condition applies. Branch push alone does not trigger this
workflow: a parent-created PR or subsequent main push will exercise it. Default
PR checkout may be a merge commit; inspect the recorded SHA/tree, not head_sha alone.

The real-PG script is designed to exercise four independent distinct admissions
while pg_locks proves global-first contention, duplicate reads, all terminal and
legacy statuses, malformed namespace/workflow rows, exact 66 MiB/one-byte overflow,
expired occupancy with a controlled physical process alive, concurrent rejected
late publications and cancellation, stale ownership and crash without a cleanup
receipt. Negative storage controls roll back uniquely owned fixture changes;
there is no DELETE or reset of retained production artifacts. The final fixture
row remains cancelled with occupancy held, without replacement.

Scope limits are explicit: the live process is a controlled synthetic holder,
not the actual PDF renderer. The publication race uses an expired owner and
proves rejection, not successful ready publication. Crash follows cancellation;
no automatic orphan-release policy is qualified. Successful complete source-locked
ready publication/retrieval remains covered by the separate existing ordinary
lifecycle proof and local prototype render test, not claimed by this new PG proof
(`successful_ready_publication_proven=false`). Full capacity-enabled PostgreSQL
ready publication and resource qualification remain open.

Local proof-harness verification: 25 cases passed (context/target guards, occupied
namespace rejection, real fixture publication fences, rollback controls, failure
evidence and workflow structure/syntax). Existing proof-contract 12 and prototype 30
cases passed again. No real PostgreSQL connection occurred here. Execution and
independent review remain pending; this is not activation-ready.

Fresh local verification on the completed proof files (three isolated pytest
processes, all exit 0):

```text
/workspace/nico-venv/bin/pytest -q tests/test_postgres_review_pdf_capacity_proof.py
25 passed in 0.17s
/workspace/nico-venv/bin/pytest -q tests/test_postgres_review_pdf_preparation_proof.py
12 passed in 7.50s
/workspace/nico-venv/bin/pytest -q tests/test_review_pdf_single_artifact_qualification.py
30 passed, 3 warnings in 12.88s
```

Logs and JUnit reports are retained in
`/workspace/pdf-capacity-qualification-handoff/`. A standalone CLI smoke with
`GITHUB_ACTIONS=false` exited 1 as required, retaining failure evidence at phase
`context` with no checks completed and `error_type=ValueError`; no connector was
used. Workflow YAML and its embedded evidence verifier were parsed by the harness.
The three warnings are existing pypdf deprecations. These local results do not
substitute for execution against the existing CI PostgreSQL service. No PR,
manual workflow dispatch, merge, deployment or activation was performed.
