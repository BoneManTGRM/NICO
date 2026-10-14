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

## Fresh-process policy failure and repair

Exact-head PostgreSQL run 38623115040 on 4f1f0937 FAILED at fresh-interpreter
retrieval with preparation_policy_changed; ledger proof passed. Same-process
restoration, rendering, locked publication and source preservation were reached,
but that run did not establish fresh-reader or downstream negative-control success.

A bounded local synthetic render reproduced the mismatch with all 798 policy
entries unchanged except _semantic_html's serialized code digest. Retaining code
attributes or populating its regex cache changes marshal reference flags without
changing the code object. Two baseline regression tests failed. Protocol 0 encodes
the complete code object without reference-sharing bookkeeping; CPython also
sorts set/frozenset values by their serialized bytes. Policy format v2 invalidates
old identities rather than accepting stale hashes. Real code bytes/constants,
configuration and renderer revision changes still change the fingerprint.

Cold/warm synthetic rendering, two fresh-process hash seeds, held code references,
regex-cache population/purge, and changed code/constant/configuration/release
controls pass. Both independent read-only reviewers found no blockers. The proof
now saves bounded completed-check/failure-phase evidence on exceptions and still
fails; exception text, credentials and source contents are excluded from that JSON.

Reconciled with main d04ac7e48a60615c07c029bfee43ee2b3c1b891e alongside this repair.
Exact-head PostgreSQL fresh-process acceptance remains pending the next normal PR
workflow; local success is not a substitute. No production settings or flags changed.

Focused verification after the policy repair: 47 API/source/proof/policy checks
passed (before the added regex-specific case); the final policy/service/proof
batch passed 46 checks, including all three policy regressions and failure JSON.
These batches overlap and are not a claim of 93 distinct checks. Existing UI and
unchanged lifecycle verification above are reused. The policy-only final run
passed all three cases. Both reviewers performed read-only independent checks.

## Exact-head CI acceptance and transport contract correction

Postgres run 38626102173/job 116065538758 on 680b149e passed the full synthetic
lifecycle, near-cap storage reload and bounded evidence verification. All 11 named
lifecycle checks were required. Artifact 11923239143 retains the seven proof files;
its catalog digest is be9fe6ef7bbff5a01a9310bf3d416b33a15d31cfe19f59dda643cbf44350d116.
This is synthetic PostgreSQL acceptance, not authentic production-size PDF or
mobile qualification; all feature flags remain OFF.

General CI job 116068205678 failed the old source-contract assertion requiring
fetch(exactRunPdfHref(...), ...). Local exact-head reproduction matched the log:
1 failed, 8 passed. Retrieval now selects either the ordinary exact-run URL or
prepared-job URL before fetch(href, ...); production transport behavior is intact.
The test now checks both selection branches and the shared same-origin GET.
Behavioral checks additionally assert the exact ordinary path and both prepared
English/Spanish paths, job/source/truth query bindings, same-origin credentials
and no-store. Original click ownership, hash verification and fail-closed tests
remain. Focused results: 9 Python transport checks and 73 JavaScript download
checks passed. No runtime, transport policy, acceptance gate or flag changed.
