# Retained diagnostic failure and bounded repair

The original fresh diagnostic, run 36290136900, failed on 2026-09-27 at
04:40:56 UTC. Neither language produced a final accepted PDF. This is separate
from the unrecoverable historical production assessment and from the completed
C++ collection qualification.

Original artifact 10923891170 contains 34 ZIP members, 35,924,072 bytes, SHA256
`d7f193a1096e38442e5783c2bcd6737fdb10526372167ff39a124a391c1cb5e0`.
Its producer is `414afd49b15dad804ade083e19f072525c36559b`, with main312693
and PDFd67 parents and the published PDF tree954104. Every member, three exact
input capsules, one result/execution pair, and 16 compressed/raw scanner outputs
were checked. The original archive remains immutable and separately retained.

## Established failures

English exhausted the unchanged 900-second final-render deadline on both existing
bounded attempts. There was no final result or PDF. The original first input also
exhausted a local 900-second replay before these performance changes. Stack samples
showed repeated cloning and recursive projection of the retained scanner register,
including clones used only by read-only score synchronization predicates.

The es-MX worker completed in 471.732 seconds but returned a blocked result:
`missing Spanish presentation translation for unavailable: eslint: eslint is not installed in the worker image.`
ESLint was genuinely unavailable. That execution state must not change.

Persisting the 160.6 MB blocked result alongside its 134.2 MB prior run then exceeded
PostgreSQL's 268,435,455-byte JSONB object-element limit. This was a distinct storage
failure, not evidence that Spanish rendering succeeded.

## Repairs

The exact bare and scanner-prefixed ESLint absence messages now have Spanish
presentation translations. Unknown English text after `eslint:` is not exempted
as a machine literal. Scanner status, completion, findings, artifacts and hashes
remain original.

Large run records use a versioned lossless zlib/base64 database envelope. Length
and SHA256 bind the complete canonical JSON; loading restores it before existing
run-integrity and review-history validation. Small records preserve their legacy
JSON bytes. Intake/browser JSON does not use the run-envelope decoder. Run,
review-history, publication-lease and browser-projection transactions remain atomic.
The decoder rejects oversized, corrupt, truncated, concatenated and trailing
compressed streams. Limits are 512 MiB expanded and 128 MiB compressed.

The actual retained blocked result was applied using the real stage-result update:
294,835,317 canonical bytes became a 17,792,230-byte envelope with an identical
logical record and valid before/after integrity. Plain SHA256:
`f485e95cd35350c419b4c8a42a2ef546b56ec174dabd67f624f47c367ee47d8a`.
Envelope SHA256:
`03e6ff9e9bd563f0a7b8e64f1045665b606f19d0e42fdc3dad1efe4fa54b29de`.
This is a data-only proof; hosted PostgreSQL execution remains required.
**Rollback compatibility:** once envelopes are written, all readers must retain
this decoder. An older reader cannot consume them. No production deployment is
included in this repair; the production hold remains.

For exact JSON graphs, two finding projections avoid redundant initial deep
copies because their final recursive projections already create independent
mutable containers. Non-JSON graphs retain historical copy behavior. Two read-only
score predicates likewise avoid a throw-away clone without altering traversal,
depth, excluded keys, strict-True checks or score-repair logic. Retained canonical
benchmarks produce identical outputs; isolated per-call savings are not a deadline
acceptance claim.

The single-pass renderer applies its original full authoritative projection first,
then uses the existing finalized-render eligibility guard to keep raw scanner
candidate payloads out of repeated presentation passes. No eligibility condition
is weakened. All projection calls remain. Every compact register metadata byte is
hash-compared before restoring the complete retained register; bool/int metadata
substitutions reject. Restoration precedes all downstream quality repair,
reconciliation, full candidate validation and canonical/artifact hash binding.
Ineligible inputs retain the original full path. Exceptions cannot publish a
compact intermediate.

A second local English replay with these projection and render changes still
expired at 900 seconds during finalization; no final PDF/result was produced.
The complete register had been restored at 478.1 seconds. Retained stack samples
showed repeated standard deep copies after restoration, so this result is not
claimed as acceptance.

An explicit report-only copy helper now handles exact builtin JSON graphs in one
memoized traversal, retaining mutable-container independence, aliases, cycles,
key order and immutable scalar identity. Unknown/custom types, non-string keys,
deep graphs and any explicit memo delegate to the standard copy implementation.
There is no global patch. Sixteen observed hot report modules opt in by import;
no validators, execution limits, result statuses or report fields are removed.
On the retained 53,808,170-byte canonical, three interleaved samples measured
0.701 seconds median for the standard copy and 0.391 seconds for this helper
(1.79x). Every clone and the original share canonical SHA256
`e38ad9f40ed5c51d303b8ca1b1a56f188d1fb5c101b19839499a8cbe98268a8e`.
The helper passed 32 focused graph/fallback tests, including a custom-metaclass
side-effect regression; 123 affected report and bilingual controls passed after
import integration. Independent read-only review checked all 172 opted-in call
signatures and 2,000 deterministic alias/cycle graphs plus eight depth boundaries;
no blocking defect was found. These measurements alone do not prove deadline
acceptance.

The third local English replay, with the copy helper, also expired at the
unchanged 900-second limit. It restored the complete register at 474.2 seconds,
but did not return a final result. Samples identified an unanchored legacy
hotspot regex retrying its path pattern on strings that cannot contain a match,
and repeated default text extraction of identical PDF bytes.

The hotspot matcher now first searches for its required `complexity` literal
using the exact same case-insensitive regex semantics, including Unicode I
variants. The original matcher, risk-pattern matcher, traversal, ordering,
exclusions and finding construction remain unchanged. The regression demonstrated
25 failures before the correction and all 26 cases passed afterward.

Five default PDF text readers share complete immutable per-page text only inside
an explicit report-attempt scope. Every glyph, identity, scorecard, semantic,
language, approval and content validator still executes. Keys are exact PDF
bytes, not filenames or asserted hashes. All pages must extract successfully
before caching. The LRU retains at most four entries and 16 MiB of PDF/text/tuple
storage; oversized entries use the complete uncached path. Exceptions are not
cached. Nested attempts, copied contexts, threads and exceptional exits cannot
leak cache entries to another completed attempt. The limit bounds retained cache
data, not transient parser allocations. Two additional observed copy sites use
the already-reviewed JSON copier without changing their detached-record behavior.

The latest delta passed 88 focused checks. Two real integration regressions also
passed: changed run/commit identities still reject on a cache hit, and the actual
report boundary releases cached data when preparation fails. These do not replace
full retained-input and hosted acceptance.

## Verification limits

Focused storage/locale/copy tests passed 56 cases. The render seam, real bilingual
visible-content and complete-canonical parity controls, single-pass contracts and
phase17 end-to-end controls passed 17 cases. Independent read-only review found
and corrected a bool/int metadata comparison gap, then found no remaining blocking
source defect. Existing C++ evidence and target findings are unchanged.

Exact large-input replays, fresh hosted source-based English/es-MX final PDFs,
PostgreSQL persistence, final integration and current-head CI remain separate gates.
No report approval, client delivery, merge or production qualification is claimed.

## Terminal local replay and presentation contract conflict

The fourth exact English replay (session61148) returned a **blocked** result at
892.204 seconds including final result serialization. It did not time out, but
this is not report acceptance. The unchanged composer rejected 1,174 retained
primary/required pages against its 60-page boundary. The intermediate base PDF
has 1,180 pages; its 2,619,169 bytes have SHA256
`26c8bd6d17e3858956d9ebb82820c90ba6ff5cf2458c567cbf9bb87fc037d206`.

The source renderer places the complete 2,499-row component table and 21,802-row
interaction table before the Evidence Appendix. Representative pages30/60/100
contain component tables; pages200/400/600/800/1000 contain interaction tables.
Page1170 still contains roadmap work-package evidence. This is not a license to
truncate the primary tail or discard source tables as legacy finding cards.
The existing source-profile tests require source tables in the final PDF.

`comprehensive_delivery_package_v2` emits exactly one client PDF and explicitly
removes legacy executive, detailed and appendix PDF paths. There is no supported
separately bound Comprehensive source-table volume. Adding one, raising the
60-page limit, or changing the PDF source tables to summaries changes the report
presentation contract. No such policy change was made. A summary in the main PDF
with complete hash-bound structured evidence is a possible owner decision, not
an acceptance result or an implemented change.

The new exact workflow contract selection plus real source-profile and layout
regressions passed **233 distinct tests**, no failures/errors/skips, in31.06s.
This preserves the current contract and does not prove the large input fits it.
English/es-MX final acceptance and hosted PostgreSQL persistence remain unproven.
No further full replay or hosted diagnostic is justified merely to rediscover
this deterministic page-budget conflict. C++ collection acceptance is unchanged.
The exact hashes and local replay limits are in `local-replay-sept27.json`.
