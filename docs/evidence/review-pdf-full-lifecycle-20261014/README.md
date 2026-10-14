# Synthetic full-path retained PDF acceptance

The existing PostgreSQL ledger proof remains unchanged: concurrent enqueue,
cross-process ownership, reclamation, stale-owner rejection and reconnect ending
at rendered_unverified. It does not itself qualify restoration/publication.

The new proof uses the same existing loopback PostgreSQL service and checks schema
availability without initialization. It creates a NEW explicitly synthetic run
through the real record transition APIs, with a genuinely rendered source package,
then persists it through ComprehensiveRunStore.create(), which creates that new
fixture's independent review-history commitment. No assessment executor runs.

The path is real store/controller restoration, admission, claim, actual isolated
Spanish child rendering (fixture cap60 seconds), source-locked ready publication,
close/reopen in a fresh interpreter, and validated retrieval with PDF digest/size,
run, historical target, locale, canonical truth and pending-approval/blocked-delivery
checks. Source record/history preservation is checked before intentional negative
controls. Stale source/owner, cancellation without rendering, and an actual
revisioned source mutation must reject old-PDF retrieval. Flags remain OFF.

A local disposable SQLite smoke verifies genuine source restoration and real child
publication. This is explicitly not PostgreSQL restart/retrieval acceptance.
The real PostgreSQL path runs in the existing PR workflow with a four-minute step
limit, no new service, no manual diagnostic and no repeated image builds.
Its outcome must be read from exact-head CI before claiming PostgreSQL acceptance.

## Remaining authentic production-input gap

Exact replay of an existing retained run requires its complete original persisted
row/payload and identity/revision/integrity/terminal metadata, plus the ORIGINAL
independent review-history commitment (event_count and chain_sha256) matching the
embedded history. A browser projection, en-run.json projection or canonical JSON
alone is not sufficient. Never initialize a missing commitment for that run.

The full retained final report package must include canonical JSON/truth digest,
report ID, source PDF bytes and checksum, Markdown/HTML, lifecycle fields and other
stage evidence. Retain its storage envelope intact. Plain JSON and codec v1/v2/v3
are supported by the current implementation; these codecs need no persistent
external dictionaries. V3 requires writable temporary storage. Compressed/expanded
bounds remain128MiB/1GiB; the small fixture does not qualify production memory/size.

Historical assessed commit and renderer release/policy are separate identities.
The current diagnostic archive's authenticity is parent-owned; this executor has
not verified that it contains the required persisted record and commitment.

The synthetic proof is NOT actual retained-report timing, production-size replay,
production acceptance, concurrent publication-lock contention proof or authorization
to enable feature flags. Live concurrent ownership remains in the earlier ledger
proof. No production settings, database pilot, assessment or C++ work changed.

## Cleanup review correction

At 8b1fbedb, a supervisor paused before operation registration could race the
immediate cleanup predicate. The new exact-class regression fails on that head.
Both cleanup paths now use ONE protocol: physically stop/join the supervisor,
then inspect outstanding operations and child/file completion before release.
Independent review examined all service/API/worker release sites and found no
remaining equivalent ordering blocker. Twenty-four lifecycle regression cases
passed before the final combined local run.

Final local verification:136 focused Python checks passed in36.78 seconds,
including the real-source/child smoke and24 lifecycle regressions. The unchanged
UI retains the prior118 passing JavaScript checks and TypeScript result. Exact-head
PostgreSQL CI is pending publication/observation; no pass is inferred from code.
