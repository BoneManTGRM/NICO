# September 27: retained hosted timeout and projection performance repair

Hosted run 36317714190, PDF source e200133, failed at 14:16 UTC. Both
English and es-MX remained blocked; all four retained renderer attempts recorded
IsolatedFinalReportCancelled. The English terminal record explicitly binds the
900-second process-local renderer deadline and confirmed worker termination.
No final PDF was produced. Original artifact 10933862166 is 34,260,527 bytes,
SHA256 de907fa75d7cf87f8ef5aecd42e33d27ef4c6115d80f33c01c84b11a15adf69f.
Its producer tree is 06a6785e8dec16e82e5ede5b2ebb7abbdfa1cea0.

The new investigation uses retained English input SHA256
6e7d7ad19efed948de6b86edff4a9bc6f02dee9da9876d908b56ae72c2e4f047.
A bounded baseline profile identifies repeated evidence-tree projection, text
rewrites, generic type dispatch, and deep copies. That instrumented local run
reached its 900-second profiling budget; it is not hosted acceptance. An earlier
sampling attempt failed due to diagnostic signal-handler reentrancy; the handler
was corrected before the retained bounded profile. Neither attempt changes the
historical hosted result.

## Repair scope

- Reuse identical short builtin-string count rewrites only within one report;
  a bounded 4,096-entry cache never crosses report calls. Long/custom strings
  preserve the original path. Every evidence row and scanner exclusion remains.
- Mapping searches avoid recursive calls for exact immutable JSON scalars.
  Ordering, repeated/shared mappings, depth limits and custom mappings remain.
- Measured runtime checks use collections.abc directly rather than typing's
  compatibility dispatch. Additional measured copy sites opt into the existing
  exact-JSON helper without changing their copy boundaries.
- That helper now starts with builtin shallow dict/list copies, memoizes before
  walking, and replaces only non-scalar children. Scalar identities, aliases and
  cycles remain intact; explicit memos, opaque values, unsupported keys and deep
  graphs still delegate the original graph to standard deepcopy.
- The hosted diagnostic runs the new projection regressions alongside its
  existing contracts. Rendering, queue and workflow deadlines, resources,
  populations, source-table exports, scores, findings, approval/delivery gates
  and production deployment guards are unchanged.

## Direct checks and review

The final helper/projection/diagnostic selection passed 115 tests, no failures or
skips. Independent review compared 150 seeded nested projection graphs against
e200133. Separate independent review checked 300 alias/cycle graphs for the
shallow-copy helper against both the original helper and stdlib. No confirmed
material defect remained. A preliminary custom-metaclass claim was retracted
when the identical baseline failure was reproduced; exact identity checks are
retained in the scalar guards.

On the full retained input, old and new helper copies have the identical input
SHA256 above; observed copy time was 2.567 versus 1.336 seconds. Other retained-
data differential checks returned identical values: mapping search 2.324 versus
0.400 seconds; path normalization 9.641 versus 4.439; a count-projection fixture
built from all retained stages 44.499 versus 6.521. These are scoped, local
measurements, not a claim about full hosted duration or timing guarantees.

The broader affected-module run exposed a global-validator binding assertion in
test_scorecard_extraction_validation_v1 after other modules mutate report hooks.
The same command failed identically on unchanged e200133 (23 pass/1 fail).
That module passed in a fresh process. A separate missing Playwright dependency
was resolved using CI's exact playwright==1.61.0. Original failures remain
recorded; affected modules are checked in separate processes without weakening
assertions. Full completion of this selection and the actual-render attempts
must be reported separately when terminal.

## Acceptance remains open

This is a reviewed performance candidate, not merge or production acceptance.
The first local isolated-worker candidate is separate from the final faster
copy-helper candidate. Both must be labeled by their actual source; neither a
microbenchmark nor the historical successful local input is hosted proof.
The final source still requires successful real English/es-MX report evidence,
PostgreSQL persistence, final PDF inspection, exact-head CI and integration.

C++ head 43aa6d7 and its completed-collection evidence remain unchanged; do not
repeat accepted native qualification. The original UBSan target finding and
production_qualified=false remain. Merge PDF first and C++ second only after
report acceptance, with the existing Vercel/Railway production hold verified.
No report approval, client delivery or production deployment is authorized here.


## Follow-up candidate after 10c840b

The published 10c840b ordinary workflow set passed, but its local English replay
still reached 900 seconds. The next source tree 8e2653e1cc300171b61dbfe824a7624793032df0
completed the same English input in 847.621 worker seconds (857.025 total),
producing 51 PDF pages. All four original source-table instances retained exact
row order/content hashes; the only additional table was the four-row authorization
matrix. Full canonical exports, table digest references, primary PDF content,
and review/delivery gates were checked. That candidate's Spanish replay failed
at 900 seconds. These are local retained-input results, not PostgreSQL acceptance.

A subsequent combined candidate also timed out on retained Spanish input
77348c48e10f738fbb2eda52c38236c392d3dc3934d81ebeb5814a2e89241a1b.
Interrupted local sessions are recorded as interrupted, not timeout or success.

This follow-up reduces redundant plain-JSON subtree copies in placeholder
sanitization, shares one ordered decision-restoration traversal, extends measured
copy-helper adoption, and avoids recursive scalar work. Plain-JSON sanitization
rejects aliases, cycles, deep graphs, custom types and unusual keys before taking
the fast path; those retain the legacy copy path. Its retained assessment output
hash stayed 1da726638482bb6aae0d449464f0218a356f99fb513e7d5122c09a413b4f2b14;
local benchmark changed from 1.362 to 0.873 seconds. This is not a full-render claim.

Text prefilters preserve Python case-insensitive Unicode matches (including
both Turkish I forms), and string subclasses retain the original regex path.
All Unicode code points were checked for ASCII-letter regex equivalence.
Scalar guards use identity comparisons, preserving custom metaclass behavior.
The risk parser only skips a known pattern when its required dot or colon is
absent. Original regex parsing remains authoritative for eligible strings.

Independent review found and corrected Unicode and custom-metaclass regressions
before the final replay restart. Eight hundred walker differential comparisons,
300 sanitizer graph comparisons, custom-copy side-effect checks, and focused
regression modules passed. Final frozen-source bilingual isolated replays and
the broader affected-module suite are in progress; no final hosted acceptance,
merge, production qualification, human approval or delivery is claimed here.
