# Bounded admission timing

This diagnostic does not repair or establish the cause of the prior 20.257-second
503. It instruments future ordinary preparation admission without new endpoints,
activation, jobs, source reads, retries, or changes to validation/deadlines.

Only `PreparationRuntime.prepare` activates the trace, after acquiring existing
capacity. Qualification, status, recovery and ordinary store reads do not emit it.
An immediate capacity rejection therefore has no admission summary. The original
HTTP response and exception mapping are unchanged.

One `nico_pdf_admission_timing` JSON caller snapshot is offered per admitted call:
- schema `nico.pdf-admission-timing.v1`; independent opaque random trace ID;
- outcome `returned` or `raised`, total elapsed and deadline remaining milliseconds;
- commit state `not_started`, `started_unacknowledged`, or `acknowledged`;
- whether guarded calls are physically pending at the snapshot;
- `durable_job_outcome=not_established_by_timing` unconditionally;
- allowlisted phase aggregates only: policy, snapshot_read, snapshot_fetch,
  decode, history_validation, record_restore_validation, report_projection,
  lifecycle_binding, enqueue.

Each phase has calls, active calls, raised calls, completed elapsed milliseconds,
remaining deadline at last start, and active span milliseconds. Active span runs
from the earliest still-open phase entry; completed time excludes active calls.
Times are inclusive, can overlap, and must not be summed. `snapshot_read` includes
connection acquisition/cleanup and all nested restoration/projection. There is no
separate connection-acquisition timer: snapshot time before fetch could include
that wait. `enqueue` measures caller wait, not later physical transaction completion.
Record restoration includes copying, integrity validation and any legacy upgrades;
its timer does not claim to isolate hashing alone.

Only the trace ContextVar is explicitly transferred into guarded worker threads;
other context behavior is unchanged. A timed-out caller may log an active phase.
Late work remains quarantined by the original guard, cannot advance admission after
expiry, and does not emit a second event. Commit fields are a caller-time snapshot,
not proof of rollback, durable absence, ready output, or physical worker exit.
Use the authorized ledger mechanism for a durable outcome, not timing inference.

Privacy and bounds: no run/customer/repository identifiers, source content, paths,
arguments, hashes, exception names/messages, or raw errors are accepted into the
schema. There are at most nine phase entries, counters cap at 9,999 and durations at
3,600,000 ms; UTF-8 JSON above 4,096 bytes is dropped. An in-process queue holds at
most 16 strings plus one being delivered. A single lazy daemon executes the log
handler. Enqueue is nonblocking; full queues and logging failures lose telemetry
instead of delaying admission. Shutdown may lose queued diagnostics. This is not a
durable audit log; absence of a log establishes nothing. No flush wait is added.

Local tests cover deterministic fake-clock timings, exceptions and commit states,
active/late threads, context isolation, bounded output/queue, a blocked logger,
real synthetic SQLite snapshot restoration/nonmutation, and existing admission and
lifecycle controls. No production payload replay, performance claim, PostgreSQL
experiment or live admission is included. Existing hosted CI/security and applicable
Postgres proof should qualify the eventual exact candidate before deployment. Any
future production trial still requires separate authorization; flags remain off.
