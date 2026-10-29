# Retained evidence boundary investigation

Base: a8cf452a844ad6d1fc44f9acbe6e3868f6769a88. Isolated investigation; neither previously published performance nor measurement-display branch is changed.

## Transformation map

| Transformation | Reads / writes | Evidence separation safe? |
| --- | --- | --- |
| Client assessment path normalization | Recurses through path/file/location fields except explicit skipped keys; repairs those values. | Not globally: nested source observations may contain matching keys. |
| Authoritative scanner truth | Reads source/scanner inventory, updates scanner records, applicability and selected narrative/count mirrors. | Not globally; field context and retained evidence affect output. |
| Finding synchronization | Recurses into records; matching finding IDs cause canonical field replacement; updates count mirrors. | Not globally; candidate records are not inert blobs. |
| Placeholder sanitization | Recursively replaces placeholder text, including nested strings. | Not globally; detaching arbitrary raw payload would change existing output. |
| Obsolete diagnostic removal | Removes specific keys/text and records path-dependent removal provenance. | Not globally; skipping a subtree could change both content and audit entries. |
| Final stage-truth normalization | Reads stage IDs and supplied evidence; replaces only each stage's top-level evidence/summary/status, then replaces the assessment stage mirror. | Yes, locally: nested evidence in the privately owned stage is not mutated. |

The map rules out a generic detach/reattach optimization across the entire installed pipeline. Existing broad transformations must continue until a separately specified contract proves which retained fields are outside their semantics.

## Implemented local boundary

`_normalize_stage_truth` first copies and certifies the canonical graph using the existing ownership helper. For an unaliased plain JSON tree, each stage gets a new shallow top-level mapping while nested evidence remains in the already-isolated private copy. This preserves the original `raw` mapping for provider reads. The private assessment mapping is reused before its stage mirror is replaced. The final assessment-stage mirror is still deep-copied, so root and assessment outputs remain independently mutable.

For shared containers, opaque/custom values, cycles or ownership fallback, the historical deep-copy path remains. No evidence, scope check, transformation, validation, identity, score, approval or delivery gate is removed. This does not certify foreign evidence; it preserves it unchanged for the existing validators.

## Verification

86 aggregate tests passed across stage-boundary tests, language truth, human-review package cleanup, retained measurements and candidate finalization. Installed EN/ES tests compare complete package equality, including PDF bytes, canonical evidence, manifests and hashes. Additional tests check alias graphs, caller nonmutation, independent mirror mutation, malformed stages, foreign scope preservation, and identical candidate population rejection. The final focused run passed 16 tests and additionally checks tampered Markdown rejection by the exact artifact validator.

Independent read-only review inspected provider/helper calls and found no nested mutation or alias blocker. Initial render fixtures lacked required stage fields and failed before rendering; fixtures were corrected without modifying validators.

## Unprofiled structural comparison

Same process, Python 3.12, no concurrent tests. Fixture: 76,547,020 compact JSON bytes, 1,681 candidates, 899 completed packets; findings contain 5,043 dicts / 8,430 lists / 794,380 scalars, depth 4; each source observation contains 54,695 dicts / 11 lists / 239,813 scalars, depth 5, repeated four times. Stage lists are each 24,415,348 bytes. Contents and some key distribution remain synthetic, not the exact production report.

Only `_normalize_stage_truth` is timed; construction, serialization and equality checks are outside the timer. Baseline forces the same copy engine's ownership flag false, reproducing previous independent copies. Order and all samples:

| Mode | Wall seconds | CPU seconds |
| --- | ---: | ---: |
| baseline | 1.340197 | 1.337367 |
| candidate | 0.598349 | 0.597686 |
| candidate | 0.604079 | 0.603501 |
| baseline | 1.277765 | 1.276705 |

Every result had canonical SHA-256 `36ba4a1a93c061862e365bcec5e01493b039129f15c9fc00e1f1a9155cc3ce86`; input hashes were unchanged. The approximately 0.7-second local reduction is useful but small relative to production preparation. It is not a whole-pipeline or production speedup claim. Hosted CI, combined qualification with pending branches and production timing are not verified. No publication, deployment, assessment or old-report rewrite is part of this investigation.
