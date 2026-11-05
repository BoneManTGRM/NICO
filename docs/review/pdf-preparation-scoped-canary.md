# Disabled, exact-source PDF preparation canary

This patch does not activate preparation or change rendering. It adds a mandatory
closed canary binding to the existing opt-in runtime and a visible cancellation
control. Existing operator authentication, retained-source validation, policy
binding, immutable assessment/report handling, review and delivery gates remain.

## Configuration for a separately approved trial

Keep `NICO_ENABLE_REVIEW_PDF_PREPARATION`, `NICO_REVIEW_PDF_PG_QUALIFIED` and
`NEXT_PUBLIC_NICO_REVIEW_PDF_PREPARATION` absent or `false` until approval.
The frontend also requires build-time `NEXT_PUBLIC_NICO_REVIEW_PDF_CANARY_RUN_ID`
and `NEXT_PUBLIC_NICO_REVIEW_PDF_CANARY_LANGUAGE`. For this proposed trial they
would be `comprun_c561d62fdef83c130805343d5766c59b` and `es-MX`. These are display
routing hints, not authorization; the backend checks the complete binding.
Other reports retain their existing synchronous download flow. Missing/malformed
frontend hints cannot activate background preparation.

Backend activation additionally requires `NICO_REVIEW_PDF_CANARY_SCOPE`, a JSON
object with **exactly** these fields:

- `customer_id`, `project_id`, `repository`, `run_id`: exact retained identities;
- `commit_sha`: assessed source revision, not the renderer deployment revision;
- `source_revision`: positive integer retained run revision;
- `source_integrity_sha256`: retained run integrity digest;
- `canonical_truth_sha256`: retained report truth digest;
- `source_artifact_sha256`: original retained PDF digest;
- `language`: `en` or `es-MX`.

Use actual authoritative retained metadata, not display placeholders or inferred
hashes. No wildcard, multiple-run list, omitted field, duplicate JSON key, unknown
field, malformed digest, or fallback to global operation is supported. The input
is limited to 16 KiB UTF-8. It is validated/copied once at runtime creation. Missing
or invalid scope makes enabled startup fail closed without starting a worker.
Renderer revision and policy remain independently bound by the existing mechanism.

For the proposed trial, the run is
`comprun_c561d62fdef83c130805343d5766c59b`, locale `es-MX`. The other exact values must
be verified before configuring it; this document is not an activation payload.
The guard applies to full admission and qualification, lost-admission lookup,
status, download, cancellation, and recovery **before** claiming/running a job.
Older or foreign queued jobs are skipped, not cancelled, altered or executed.
The scope restricts the retained source, not a particular operator: existing
operator authorization remains unchanged. Two authorized operators requesting the
same bound source use the existing deterministic job/lease deduplication.

## Browser flow and cancellation

The existing authenticated report Download button uses the existing frontend
proxy when its build-time flag is enabled. A visible EN/es-MX Cancel preparation
button appears while admission/status is pending. Cancellation intent is saved
before sending a source-bound request to the existing `/review-pdf/{locale}/cancel`
endpoint. Uncertain admission is recovered with GET; it never reposts admission
to find a job to cancel. Reload retains unresolved cancellation intent. Browser
session storage is required for cross-reload recovery; in-memory intent still
protects the active operation if storage is unavailable.

Cancellation is a ledger/lease operation, not proof of physical exit. The response
explicitly leaves `physical_worker_exit_confirmed` null. UI says cancellation was
recorded and process exit is unconfirmed; existing worker fencing and quarantine
remain responsible for safe capacity release. Closing a page only stops observing.
The cancellation endpoint now has a five-second caller/commit guard; an uncertain
commit is not reported as successful, and late operations quarantine the read slot.

If publication wins, UI says preparation finished before cancellation and does not
automatically download. A later explicit Download may retrieve the verified PDF;
reload cannot. A confirmed cancelled identity remains terminal and cannot silently
re-enqueue. If cancellation occurs before admission, a later explicit click can
start preparation. No cancel operation grants human approval or client delivery.

## Qualification and rollout boundaries

Tests use synthetic records, mocks and existing isolated SQLite fixtures. They do
not establish this new patch's hosted PostgreSQL qualification or production
behavior. Existing PG lifecycle evidence on the base revision is separate evidence;
required exact-head hosted checks remain necessary before deployment.

After explicit approval, deploy the guarded backend with its verified exact scope
and the two existing backend flags true, verify readiness, then rebuild the frontend
with its existing public flag true. Keep release identity labels consistent. Use
one existing retained Spanish report, no new assessment. Existing admission20s,
job900s/max2attempts/lease30s, browser bounded observation and final hash/source/gate
validation remain unchanged. The patch does not reduce rendering CPU time.

Rollback: request cancellation through the visible UI where applicable; record
whether completion is confirmed or unknown. Set the three flags to false and
redeploy/rebuild. Flag changes are not instantaneous cancellation and do not prove
worker exit. Preserve ledger evidence; do not delete or rewrite reports. Re-enabling
with a different scope requires another deliberate configuration/approval decision.
No schema changes, provisioning, credentials, new permissions, or database-pilot
activation are part of this patch.
