# NICO Mid and Full Assessment Recovery

## Purpose

Mid and Full assessments execute synchronously while their durable state is stored in Postgres. A backend restart can interrupt repository evidence collection, scanner attachment, scoring, report generation, or approval-request creation. Recovery must continue the same authorized run without creating a second run, scanner, report, approval, delivery grant, or receipt.

NICO now persists the run identity before execution, checkpoints each orchestration step, reconciles stale active records, and requires an authenticated operator to claim a same-run resume.

Recovery does not authorize score changes or client delivery.

## Durable checkpoint model

Every Mid and Full run receives its durable run ID before orchestration starts:

- `midrun_*` for Mid;
- `fullrun_*` for Full.

NICO records a checkpoint at:

1. preflight;
2. each step start;
3. each step completion;
4. each step failure;
5. orchestration finalization.

Each checkpoint contains:

- current step;
- phase;
- heartbeat timestamp;
- completed-step list;
- completed-step count;
- SHA-256 of the retained progress state;
- recovery attempt count.

Checkpoint persistence keeps the original repository, customer/project scope, authorization metadata, completion intent, scan ID, snapshot identity, report ID, and approval ID. PDF bytes and one-time submission capabilities are not duplicated in the checkpoint record.

## Stale assessment detection

The environment variable is:

```text
NICO_ASSESSMENT_RECOVERY_STALE_SECONDS
```

The default is 900 seconds. Values are bounded between 60 seconds and 86,400 seconds.

A record may become `recovery_required` only when:

- its workflow is `mid_assessment` or `full_assessment`;
- its durable status is `running`, `resuming`, or `planned`;
- Postgres persistence is active;
- its latest checkpoint heartbeat or update time exceeds the stale threshold;
- an atomic compare-and-set transition succeeds.

Recent active records are preserved during rolling deployments. Missing or malformed heartbeat time is treated as stale because continued execution cannot be proven.

Completed, failed, blocked, approved, delivered, and cancelled records are not changed by reconciliation.

## Startup reconciliation

Production startup runs bounded reconciliation over at most 1,000 assessment records.

Startup reconciliation:

- does not resume any run;
- changes only stale supported active records;
- preserves existing evidence and artifact identities;
- records the previous status, stale age, detected time, and recovery attempt;
- writes a bounded audit event;
- remains blocked when durable Postgres is unavailable.

Memory fallback is never represented as restart-safe.

## Operator inventory

Use:

```text
GET /operations/recovery/assessments
```

Optional parameters:

```text
refresh=true
limit=200
```

The endpoint requires `X-NICO-Admin-Token` and returns bounded structural state only:

- run ID and workflow;
- repository and customer/project scope;
- status and timestamps;
- current checkpoint and completed steps;
- scan ID;
- snapshot ID and commit SHA;
- report and approval IDs;
- recovery reason and attempt count.

It does not return raw request bodies, source snippets, scanner output, credentials, provider responses, exception messages, delivery tokens, or PDF bytes.

## Same-run resume

After human review, resume with:

```text
POST /operations/recovery/assessment/{run_id}/resume
```

Body:

```json
{
  "actor": "operator-name"
}
```

The resume process:

1. verifies operator authentication;
2. verifies the record is `recovery_required`;
3. verifies repository, customer/project scope, `authorized_by`, `authorization_scope`, and authorization confirmation;
4. verifies snapshot identity is either not yet captured or complete as both snapshot ID and commit SHA;
5. verifies any bound scanner belongs to the same assessment run;
6. blocks assessment continuation while the bound scanner itself requires recovery;
7. atomically changes the same run from `recovery_required` to `resuming`;
8. increments the recovery attempt;
9. invokes the existing Mid or Full status-continuation path;
10. checkpoints every resumed orchestration step;
11. reuses deterministic report and approval identities;
12. returns the same run ID.

Concurrent resume requests cannot both claim the same record. Later requests observe `resuming`, `running`, or a terminal state and return idempotent reuse without starting a second continuation.

## Artifact duplicate prevention

Full report and approval creation already use deterministic identities derived from the run, scanner, and report identity. Mid draft reports are derived from the exact run, snapshot, truth model, and review packet. Mid approval requests are bound to the exact draft and item-level review state.

Recovery calls those existing idempotent paths. It does not create a second artifact path.

Existing report and approval IDs remain attached to the assessment record. Delivery grants and receipts are outside the recovery mutation boundary.

## Failed resume behavior

When a resume invocation raises an exception or produces a failed/blocked continuation result, NICO attempts an atomic return to `recovery_required`.

The record retains:

- recovery attempt;
- operator identity;
- bounded error class;
- human-review requirement;
- client-delivery denial.

Raw exception text is not returned or stored in recovery inventory.

## Semantic readiness

The recovery routes are required production routes:

```text
GET /operations/recovery/assessments
POST /operations/recovery/assessment/{run_id}/resume
```

Semantic readiness adds the advisory check:

```text
assessment_recovery_queue_clear
```

A non-empty or stale assessment recovery queue degrades readiness and requires operator attention. It does not falsely state that Postgres schema or scanner execution is unavailable.

## Operator acceptance procedure

1. Confirm Vercel and Railway run the exact same current `main` SHA.
2. Confirm `/operations/storage-schema?refresh=true` is ready.
3. Open `/operations/recovery` and enter the admin token.
4. Refresh assessment and scanner reconciliation.
5. Review the saved repository, scope, authorization, checkpoint, snapshot, scanner, report, and approval identities.
6. Recover a bound scanner first when required.
7. Resume one reviewed Mid or Full run.
8. Confirm the same run ID is retained.
9. Confirm completed steps and existing artifact IDs are reused.
10. Confirm no duplicate report or approval record is created.
11. Confirm readiness returns to clear or ready after recovery.
12. Keep client delivery blocked until the normal item-level review, approval, controlled delivery, and receipt controls pass.

## Scope boundary

This stage implements Mid and Full checkpointing, stale reconciliation, atomic same-run continuation, and duplicate artifact prevention through existing deterministic paths.

It does not yet prove:

- scheduled backup creation;
- restore execution;
- point-in-time recovery;
- multi-region failover;
- disaster-recovery timing objectives;
- automatic client communication;
- automatic production rollback.

Those remain later Phase 3 stages.
