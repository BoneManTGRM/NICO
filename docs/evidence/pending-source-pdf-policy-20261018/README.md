# Pending-source review PDF policy qualification

Base: `0a3ad3f94be551513401bb955bf54ac35494ad53`.
This is a source/test change with all existing rollout gates unchanged. It is not
production activation or exact-candidate PostgreSQL qualification.

The queue derives a required artifact mode from the authoritative pending source
and the installed renderer's frozen-source decision. A locale match alone does
not imply frozen bytes: existing presentation/integrity wrappers can regenerate
a same-locale draft. Frozen pending-source PDFs and regenerated pending-source
localized drafts have distinct job identities and strict header requirements.
Approved/rejected sources remain excluded. No source/history/approval/delivery
record is changed by qualification or rendering.

Mode is bound into the deterministic job identity, versioned runtime policy,
status, child output, ready publication and retrieval. Both server and browser
reject inherited acceptance authority. The worker validates the generated draft's
existing requires-new-approval/invalidation headers; it does not change them to
pass validation. Frozen-source responses gain explicit invalidated=false only
when that previously absent header is needed for the queue's strict wire contract.

For a new UI request requiring locale reapproval, an authenticated read-only
qualification GET must prove the pending-source policy before the explicit POST.
The POST independently revalidates admission. Job identity/mode must remain stable
through polling and retrieval. Lost admission responses retain the existing GET-only
recovery behavior. No automatic fallback to synchronous regeneration occurs when
qualification fails. Flags-OFF ordinary downloads remain unchanged.

Historical jobs without the new required mode are not upgraded or reused. The
policy version also invalidates older identities; no job rows are deleted.

## Verification

- Five original regression cases failed because omitted/false localized approval
  headers and false frozen-source inheritance were accepted before this change.
- 272 Python checks in 12 fresh pytest processes passed with no skips/xfails.
  Includes two real isolated-child fixture cases (English source to English and
  Spanish), source/history preservation, mode/locale/source/policy binding,
  header omission/inheritance rejection, qualification without enqueue, dedup,
  cancellation, lease/timeout/uncertain-commit recovery and policy stability.
- 123 JavaScript review-download, Workspace fallback and proxy checks passed.
  Includes derivative eligibility, status/header tampering, dedup and lost-response
  GET-only recovery. TypeScript `tsc --noEmit --incremental false` passed.
- PostgreSQL tests here are mock/proof-contract tests. Local state tests use only
  disposable synthetic fixture storage. No real PostgreSQL was contacted.

## Activation prerequisites, deliberately separate

Independent review and normal exact-candidate CI are pending. Real PostgreSQL
lease/ready publication/fresh-process retrieval still requires candidate evidence
from the existing isolated service; no extra workflow was dispatched. Authentic
production-size record restoration, admission and retrieval timing, full rendering
within the existing 900-second budget, and memory limits remain unqualified.

Fleet-wide capacity, queue admission limits, retained-artifact TTL/storage budget
and retry policy are unresolved activation prerequisites. This patch adds no
workers, capacity, schema, environment variables, installations or purchases.
It changes no production settings, credentials, source assessments or approved
editions. Approved-source expansion is excluded. C++ remains paused and the
unrelated database pilot remains on hold.

## Independent-review correction: frozen source digest

Review of `7c31deebc4eb236b4b8593d85a95ab271a2f9e6f` identified that
self-consistent output hashes did not establish frozen-source identity. Three
new regressions failed on that exact head: a different valid PDF was accepted
by worker validation, ready publication and retained retrieval, even with all
hash declarations updated consistently. The same-locale fixture also used an
unrelated source digest; its positive case now binds the actual source bytes.

Frozen mode now additionally requires the computed PDF digest to equal the
immutable `source_artifact_sha256` in the job identity, before either full-parser
validation or the publication/retrieval fast path can return. Localized-draft
mode deliberately permits newly rendered bytes, with its existing source and
approval gates unchanged. An explicit positive derivative control preserves this.

Final correction verification: 276 Python cases in the same 12 isolated suites
passed. Browser/TypeScript source is unchanged; the preceding 123 JavaScript and
TypeScript results remain applicable. This correction changes no capacity,
activation, authentication, source lifecycle, score, or acceptance policy.
