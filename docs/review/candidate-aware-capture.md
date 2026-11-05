# Candidate-aware capture integration

This branch depends on PR #1843 (`be3a2e5326de7042a84243a0e536517a1f7752b9`). It does not alter that branch. Hosted CI, merge and production verification remain required.

The ordinary snapshot scanner worker captures observations once after its retained detailed findings are available and before deleting its existing verified workspace. Repository profiling no longer performs the earlier capture. A persisted reservation prevents another capture after a restart, including interruption before completion. Missing capture remains missing; scoring cannot resurrect an older capture after a reserved new attempt.

Selection considers at most 10,000 retained detailed candidate rows. Supported-rule paths precede other candidate paths, each group sorted lexically; duplicate paths are read once. This is prioritization of review assistance, not candidate dismissal. All original candidates remain in the register. The retained accounting distinguishes a truncated inventory from complete enumeration of retained details, and scanner collection completeness from inventory completeness. Counts do not establish exhaustive scanner coverage.

The shared five-second deadline starts before normalization and selection. Git commands use the remaining deadline, bounded streaming output, literal selected paths, no lazy fetching and no replacement objects. Only regular blobs from the exact Git revision are parsed; symlinks, submodules, traversal and missing paths are not followed. No source executes. Parsing retains the prior cooperative deadline between bounded 256 KiB parses; this is not a hard real-time parser kill guarantee.

Metadata and source reads share an 8 MiB input ceiling. Metadata streaming is additionally capped at 256 KiB. Failed source reads consume their reserved bytes. The entire observation envelope, including scope and accounting, is measured as serialized UTF-8 bytes with ASCII escaping; it remains within 2 MiB. A conservative envelope allowance prevents path/scope metadata from silently exceeding the payload limit. Raw source is not persisted or kept beyond the existing workspace lifetime.

Scoring retains bound observations as internal stage evidence for final publication. Publication reanalyzes finalized candidate rows with the existing PR #1843 freshness checks. Original investigations, candidate evidence, scores, human dispositions and delivery gates remain intact. Read-only diagnostics consume the same stage evidence. Historical runs remain readable without mutation.

The separate queued worker-contract/C++ channels do not acquire candidate observations through this ordinary worker. They remain explicitly unsupported; this change does not activate the C++ or database pilot work.

## Local qualification

The exact-source replay used revision `5e9c6db3381a7d92c85ae6bf545bd572fc21d589`, its verified 2,585-file inventory and all 1,678 retained candidates. Scanner outcomes were replayed from retained candidate evidence; no scanner or live assessment was rerun. The actual worker lifecycle, temporary workspace deletion, final enrichment and real UI projection were exercised. Separate installed English/Spanish renderer tests validate artifact hashes and gates.

Baseline final valid analyses: 37. Candidate-aware final valid analyses: 924. The remaining 754 are unresolved: 568 missing-source, 68 source-identity mismatch, 44 ambiguous expression, 35 specialist-rule, 24 unsupported dependency and 15 line-mismatch cases. These are bounded structural analyses, not confirmed findings or human decisions.

Observed capture: approximately 2.20 seconds; metadata plus source charged 4,755,325 bytes. The conservative serialized envelope was approximately 2.066 MB, below 2,097,152 bytes. No timeout occurred in this replay. Overall replay time was approximately 8.46 seconds including investigation, finalization and UI validation; it is not a production latency benchmark. Baseline capture used 8,388,504 source bytes. Its legacy per-observation accounting omitted envelope overhead; the new check includes it.

Tests cover duplicate/order behavior, invalid paths and foreign scope, tracked symlinks and changed checkout content, missing and capped inventories, input/UTF-8 output budgets, timeout/overrun, partial scanner failure, reservation/repeat behavior, cleanup, stage handoff, diagnostics, installed bilingual artifacts and UI freshness. Hosted Python and production behavior remain unverified until the normal review/release process completes.

Rollback is a normal code revert. Do not rewrite retained reports or delete evidence. Reverting does not reinterpret old observations or grant human approval.
