# NICO Scanner Restart Recovery

## Purpose

Hosted scanner execution uses a process-local worker thread while scanner state is written to durable storage. A backend restart can terminate the thread but leave the durable scanner record in `queued` or `running`. Without reconciliation, that record appears active forever. Repeated manual retries can also create duplicate scanner executions and conflicting evidence.

NICO scanner recovery converts stale persisted work into an explicit operator-reviewed state and resumes the same scan identity through an atomic Postgres claim.

## Recovery states

Normal scanner states remain:

- `queued`
- `running`
- `complete`
- `failed`
- `error`
- `blocked`

Recovery adds:

- `recovery_required`

A scanner becomes `recovery_required` only when:

1. its persisted status is `queued` or `running`;
2. durable Postgres is active;
3. its last update is older than the configured stale threshold;
4. an atomic status transition succeeds.

Recent scanner records are preserved during rolling deployments. Missing or malformed update time is treated as stale because continued execution cannot be proven.

## Stale threshold

The environment variable is:

```text
NICO_SCANNER_RECOVERY_STALE_SECONDS
```

The default is 600 seconds. Values are bounded between 60 seconds and 86,400 seconds.

The threshold is not a scanner timeout. It is the minimum age before process-local execution may be classified as interrupted.

## Startup reconciliation

The production application runs reconciliation while installing production routes.

Startup reconciliation:

- reads at most 1,000 scanner records;
- examines only `queued` and `running` records;
- preserves recently updated work;
- atomically changes stale work to `recovery_required`;
- records the previous status, detected time, stale age, and recovery attempt count;
- never starts a scanner automatically;
- never changes scores, reports, approvals, or delivery records.

Memory fallback is not treated as durable recovery. Reconciliation remains blocked when Postgres is unavailable.

## Operator inventory

Use:

```text
GET /operations/recovery
```

Optional parameters:

```text
refresh=true
limit=200
```

The endpoint requires `X-NICO-Admin-Token`.

The response contains bounded structural data only:

- scan ID;
- bound assessment run ID;
- customer/project scope;
- repository identifier;
- scanner status;
- timestamps;
- requested tool names;
- recovery reason and attempt count.

It does not include scanner output, request bodies, credentials, tokens, raw exceptions, or provider payloads.

## Same-ID resume

After human review, resume with:

```text
POST /operations/recovery/scanner/{scan_id}/resume
```

Body:

```json
{
  "actor": "operator-name"
}
```

The resume process:

1. verifies the admin token;
2. verifies that the durable record is `recovery_required`;
3. verifies repository, `authorized_by`, and `authorization_scope` metadata;
4. performs one atomic Postgres transition from `recovery_required` to `queued`;
5. increments the recovery attempt;
6. starts the process-local scanner thread using the same scan ID;
7. retains normal scanner evidence and completion persistence.

Concurrent resume requests cannot both claim the same `recovery_required` record. The winning request changes the durable status first. Later requests observe `queued`, `running`, or a terminal state and return idempotent reuse without starting a second thread.

If thread creation fails after the claim, NICO returns the same record to `recovery_required` and stores only the exception class.

## Readiness behavior

The recovery routes are required production routes.

Semantic readiness adds the advisory check:

```text
scanner_recovery_queue_clear
```

A non-empty recovery queue degrades operations readiness and requires operator attention. It does not claim that core Postgres storage is unavailable. Client delivery remains separately governed and is never authorized by recovery state.

## Operator procedure

1. Open the production Recovery page.
2. Enter the operator admin token.
3. Refresh reconciliation.
4. Confirm the exact Vercel and Railway release SHA in Operations.
5. Review each repository, run binding, requested tool set, prior status, and recovery reason.
6. Resume only work that is still authorized and required.
7. Confirm the same scan ID moves to `queued`, then `running`, then a terminal state.
8. Refresh the parent Mid or Full run through its existing status endpoint.
9. Verify that reports and approvals are reused rather than duplicated.
10. Keep client delivery blocked until the normal human review and delivery controls pass.

## Scope boundary

This stage provides scanner restart reconciliation and duplicate-resume prevention.

It does not yet prove:

- automatic Mid or Full run recovery;
- report generation recovery after an interrupted process;
- approval-transition recovery;
- delivery-grant or receipt recovery;
- backup creation or restore execution;
- disaster recovery.

Those remain later Phase 3 stages.
