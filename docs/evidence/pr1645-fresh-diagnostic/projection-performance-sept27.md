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
