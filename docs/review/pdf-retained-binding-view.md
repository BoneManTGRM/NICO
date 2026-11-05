# Read-only retained PDF binding view

Preparation flags remain disabled. This projection neither enables preparation nor
proves production lifecycle qualification. Deployment and any trial require separate
approval.

After deployment, an already authenticated operator may navigate normally to:

```
https://app.nicoaudit.com/api/nico/assessment/comprehensive-run/comprun_c561d62fdef83c130805343d5766c59b/review-pdf/es-MX?retained_binding=true
```

This uses the existing authenticated browser proxy, without JavaScript injection,
credential extraction or a hidden request. The small JSON response can be inspected
in the browser. The route is also parameterized for other valid run IDs and the two
supported locales under the same existing operator authority. Proof-only sessions
remain excluded. Extra/duplicate query parameters, wrong suffixes and invalid run or
locale syntax are rejected. No new access permission is added.

A successful response has schema `nico.pdf-retained-binding.v1`, status `available`,
`snapshot_validated: true`, and `binding` containing exactly the ten existing canary
scope fields. It also identifies `source_report_language`, terminal status and the
unchanged review/delivery gates. `activation_authorized` and `lifecycle_qualified`
remain false. Copy only the complete `binding` object into the future approved
`NICO_REVIEW_PDF_CANARY_SCOPE` configuration. Do not configure from a partial or
unavailable response. Do not substitute display placeholders for tenant IDs.

`source_artifact_sha256` is the PDF digest from the validated original retained final
report package. It is not the requested Spanish derivative digest. The requested
`language` selects the future canary output; `source_report_language` explains which
original PDF the source digest represents. The assessed `commit_sha` is not the
renderer deployment commit. `source_revision` and `source_integrity_sha256` bind the
stored run, not the ZIP manifest or report's canonical JSON digest.

The reader uses `load_without_maintenance`: one stored snapshot with existing
review-history commitments and record integrity validation. Missing commitments
fail closed, rather than being initialized. It uses the same in-memory validated
artifact projection as preparation admission, checks identity/revision/integrity
consistency, then returns allowlisted metadata only. It never calls ordinary status,
continuation, intake reconciliation, schema initialization, cache refresh, rendering,
job admission, cancellation or a production record writer. Existing report bodies
are read internally for validation but never returned.

The caller has a 20-second deadline, one metadata slot and the existing shared heavy
publication slot. Busy returns no binding. Timed-out or failed validation returns
only `unavailable`, no raw error or partial metadata. Both slots stay quarantined
until the underlying operation physically returns. Threads/database reads cannot be
forcibly killed safely; a blocked driver may keep the slots held beyond the response
deadline. Do not repeatedly retry such a failure. Output is limited to 20 KiB UTF-8;
the binding separately satisfies the existing 16 KiB scope parser limit. The proxy
keeps its existing 30-second metadata request deadline and no-store/private response.

Snapshot metadata can become stale after the response. The guard still rechecks the
full authoritative source at admission, rendering/publication and retrieval. A
changed revision must reject the prior binding; do not weaken or automatically
refresh the guard to force a trial through.

Local qualification uses synthetic records and SQLite query-only connections, with
byte-for-byte database nonmutation checks and actual controller/package validation.
It is not a new PostgreSQL or production performance qualification. Existing base
CI evidence remains separate; exact-head hosted checks and deployment approval are
still required. No large production report was read or rendered during development.
