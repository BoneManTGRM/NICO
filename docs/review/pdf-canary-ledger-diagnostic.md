# Disabled-canary ledger observation

This diagnostic is read-only. It does not admit, claim, recover, cancel, delete or
modify a job; initialize schema/commitments; reconcile an assessment; or render a
PDF. Existing preparation flags must remain off. This change is not activation or
permission to retry the failed canary.

After separately approved publication, exact-head hosted checks and deployment, an
existing authenticated operator can navigate normally in the browser to:

```
https://app.nicoaudit.com/api/nico/assessment/comprehensive-run/comprun_c561d62fdef83c130805343d5766c59b/review-pdf/es-MX?canary_ledger=true
```

The existing proxy/session is used; no injected fetch, credential extraction or
hidden browser API is needed. Existing authorization applies, including rejection
of production-proof-only sessions. The route is available with preparation disabled.
Extra or duplicate query parameters and artifact/cancel suffixes are rejected.

## Scope and semantics

The diagnostic requires the existing strictly validated `NICO_REVIEW_PDF_CANARY_SCOPE`
configuration and the request must match its run and locale. Missing/invalid scope
or either enabled backend preparation flag prevents connecting. Nothing is hardcoded
to a production identity. The existing canonical PostgreSQL connection is reused;
there is no fallback or independent credential source.

The SQL selects rows whose relational tenant/project and payload workflow/run/locale
match the configured canary. It deliberately does **not** join current assessment
revision/integrity or filter renderer/policy: such filters hid obsolete rows in the
ordinary lookup. It compares all ten configured source fields and returns only
allowlisted mismatch field names, never the foreign field values. Rows outside the
configured relational tenant/project, with malformed/unattributable run/locale, or
with another workflow are excluded; this is not a global forensic inventory.

The response schema is `nico.pdf-canary-ledger-read.v1`:

- `query_complete=true`, `status=complete`: the scoped query finished without row
  truncation and cleanup succeeded. `scoped_rows_present=false` is meaningful only
  here, at this read's snapshot; it does not prove no future/in-flight commit exists.
- `status=partial`: more than 32 rows matched. Only 32 are returned. Positive presence
  may be established; absence of an exact source match stays null unless the query
  completed. A matching sentinel row can prove presence without being displayed.
- `status=unavailable` or `busy`: presence fields are null, not false. No partial
  rows are returned on errors, malformed metadata, timeout or cleanup failure.
- `exact_source_row_present` compares the ten configured stored source fields. It
  does **not** establish job identity digest validity, current renderer policy,
  readiness, safe retrieval or approval. `job_integrity_verified` remains false.
- Row metadata contains a format-validated job ID or null, allowlisted state,
  payload/relational-state consistency, source mismatch field names, validated
  renderer/policy hashes or null, bounded attempts and nullable lease/deadline
  booleans. No job payload, PDF bytes, report body, customer record or raw error
  leaves the database as output.
- `physical_worker_exit_confirmed=null` and `activation_authorized=false` always.
  Inactive/expired leases do not prove physical process exit.

The source binding is the retained configured revision, not a request-supplied
replacement. Preserve all rows and configuration; do not use this view to silently
refresh the canary or re-enable recovery.

## Bounds and qualification

A fresh idle canonical connection starts `BEGIN READ ONLY`. Transaction-local limits
are 3 seconds per statement, 1 second for locks, and 5 seconds idle in transaction. The read-only setting is verified before
querying. SQL LIMIT 33 and fetchmany(33) provide 32 rows plus one truncation sentinel.
Output is capped at 24 KiB UTF-8. The caller deadline is 10 seconds with one process-local slot;
a late connection/query/cleanup holds the slot until physical return. Python cannot
forcibly kill a blocked driver. Such uncertainty returns no false absence. Connections
are rolled back and closed; no commit is issued.

Local tests use synthetic connection seams and assert SQL/parameters, privacy,
strict scope, row/output caps, timeout quarantine, cleanup and authorization. They
are not PostgreSQL execution proof. The existing synthetic PostgreSQL lifecycle
proof now also executes this diagnostic against its already-owned ready row, a
changed expected revision and a nonexistent synthetic run, with flags off and
source/job equality checks. No new workflow, infrastructure or schema is added.
Exact-head Postgres Restart Proof must pass before claiming real-query qualification.
The local environment has no configured PostgreSQL test target.

## Deployment and interpretation plan

After separate authorization: publish, complete required checks (including the
updated Postgres Restart Proof), normal merge controls, then deploy with all
preparation flags still false and the existing exact canary scope unchanged. Perform
one browser GET. Retain the response plus observation/deployment identity. If partial
or unavailable, stop and report the limitation rather than repeatedly querying or
activating preparation. A row, especially an obsolete one, requires separate review;
this patch provides no mutation path. Rollback is ordinary code rollback with flags
still false; never delete ledger evidence. No production query or trial was performed
while preparing this patch.
