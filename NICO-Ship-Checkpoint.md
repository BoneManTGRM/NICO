# Current native result and bounded build correction — 2026-09-26

Full native run 36241917330 on parent 3cbe702 completed with failure at 14:43 UTC.
Baseline 377/377, compiler/static contexts 475/475, functional 6/6 and ASan 377/377
completed successfully. UBSan retained the same failed net_tests (376/377 passed).
The Clang/GCC link repair got past mpgen, then the serial fuzz build timed out at
1200.132 seconds. Replays and campaign remain unexecuted. Hash-verified retained
evidence reconstructs identically before and after this correction.

Runtime plan v3 now schedules at most two fuzz build workers, keeping campaigns
serial and historical v1/v2 commands exact. Source, populations, instrumentation,
deadlines, resource ceilings and qualification gates are unchanged. Local workflow
contracts: 1375 passed, one native-toolchain skip; 24 new cases. Independent
review: no blocking defect, 45 affected tests passed. Actual two-worker Bitcoin
completion and memory use remain unproven. Evidence and exact limits:
docs/evidence/pr1644-fuzz-build-scheduling/README.md.

Existing f32 native run 36247114532 and diagnostic 36247114503 were pending at
the last check; no running qualification was cancelled or manually duplicated.
New candidate CI/native evidence must be evaluated at its own published head.

PDF head c6f9f4c7ad53c791d53e0a10dcb303e190078394 passed both normal CI paths;
remediation attempt 2 passed after an HTTP 500 in the first attempt. Actual
assessment comprun_34a469900baa742c0d557f42634b318f remains blocked at final report
generation on frozen 312693443b1e, revision 67, with no final PDF. Supported
review/recovery access exposes no retained-input export without operator approval;
approval must not be manufactured to obtain that input. Actual-input EN/es-MX
rendered acceptance requires a legitimate export or equivalent supported access.
No repeated recovery, raw-record diagnostic reroute, report approval or client
delivery was attempted. Neither PR is merged; production remains unqualified.

The owner authorized publication and merging when ready without another permission
request. All original C0-C19 gates and both PR histories remain authoritative.
Earlier snapshots follow unchanged; their running states are historical.

---

# Current authorization and review — 2026-09-26

The owner explicitly authorized finishing both existing PRs and merging when
ready. This supersedes historical requests to seek merge permission again; it
cannot establish missing acceptance evidence or approve client delivery.

This commit corrects fuzz abort and prefix retention. 1351 local contracts passed,
one native-toolchain test skipped. Independent affected verification passed232;
full applicable code review found no further concrete blocker. Retained native
run36235924285 reconstructs identically and remains failed. Full run36241917330
on parent3cbe702 is still executing; this new executor requires native verification.
See docs/evidence/pr1644-fuzz-abort-retention/README.md.

PDF PR1645 now contains6a8cebdd with truthful final-PDF availability checks.
Authenticated actual-run review succeeded, but final PDF download was unavailable.
Supported exact-run recovery identifies a final-render deadline on NICO source
312693443b1e; the owner's authorized bounded same-run resume returned the same
blocked final stage. No replacement assessment, approval or delivery was created.
Actual-input rendering acceptance remains open. Neither PR is merged.

All prior ledgers and original requirements follow unchanged as historical evidence.

---

# PR #1644: collection verified; fuzz toolchain link correction prepared

Full run 36235924285 completed on `8dc23f905f42ef63123edf998610d55c0f313070`.
Baseline 377/377, compiler 475/475, static contexts 475/475, functional 6/6,
and ASan 377/377 passed. UBSan retained the same one failed `net_tests` case.
The new collection policy continued into fuzz staging/configure, then stopped
at a separate Cap'n Proto link failure (`__cxa_call_terminate`, exit 2, no timeout).

The next correction selects `/usr/local` GCC 14 headers/runtime for Clang in the
pinned image and requires owned negative/positive Cap'n Proto link and sanitizer/
fuzzer controls during image construction. Local contracts: 1324 passed, one
native-toolchain skip. Exact-image and full Bitcoin execution are not yet proven
for this correction. Details and retained evidence:
`docs/evidence/pr1644-clang-gcc-runtime-alignment/README.md`.

The UBSan finding, actual authenticated assessment replay, complete review, and
production-shipping hold remain open. Neither PR is merged.

---

# NICO — completed-failure collection correction; native qualification still required

Continue existing PR1644 and PR1645. This ledger does not authorize merge, production shipping, report approval or client delivery. Preserve every original C0–C19 requirement, fixed source/populations, isolation/resource boundaries, genuine human approvals and complete independent-review requirements.

## Immutable continuity

Candidate parent: b7a16195e56fc550025fd9e86bcbdb0aa8bdbe85, tree ff1db0d025f366a914d14649812a2a3803d2346b, branch fix/cpp-runtime-scratch-retention. Preserve the entire [b7 checkpoint and predecessor chain](https://github.com/BoneManTGRM/NICO/blob/b7a16195e56fc550025fd9e86bcbdb0aa8bdbe85/NICO-Ship-Checkpoint.md), [latest full-run failure](https://github.com/BoneManTGRM/NICO/pull/1644#issuecomment-5841229047), and [unpublished timeout-extension boundary](https://github.com/BoneManTGRM/NICO/pull/1644#issuecomment-5841011521). The separate PDF candidate remains 8dad406085c1364ce153a0e3381f16058baccc04; preserve its complete [ledger/review chain](https://github.com/BoneManTGRM/NICO/blob/8dad406085c1364ce153a0e3381f16058baccc04/NICO-Ship-Checkpoint.md). Reconcile this shared ledger before integration. Main312693443b1e70c8a065de2c4e9ca329281d162a is unchanged.

## Actual isolated measurements

Diagnostic36188616676/job108290694130 completed successfully. Artifact10892711952 is373152bytes, SHA2568aeffd523b95ec838e7a4e064827e2504c6266c53e3cb28829b76cf6aa6be273. It ran both cases, not a skipped diagnostic. Independent reconstruction checked58 operation outputs, bound source/context/JUnit/plist evidence, instrumented binary identity, original300/120-second limits, and sandbox cleanup.

The frozen Bitcoin cluster_linearize_tests case passed alone in158.828seconds; the generated Clang context c2d48aa8de514849e4167b32061fe921be8df2b06bca621bb2c96ba4990ef65e passed in85.985seconds. No OOM events were recorded. CPU measurements are unavailable and the rebuilt diagnostic image differs from the historical image. These results support a contention hypothesis, not proof of the exact hardware cause or of full-run two-worker success.

Full run36188616532 remains a failure: ASan376/377 and static474/475, with UBSan/fuzz unexecuted. The isolated result never replaces its receipt. Historical36167659433 runtime/static bytes were reconstructed under their original v1 plan/v2 fallback and remain incomplete. Preserve all earlier failed artifacts and frozen targets.

## Scheduling-only correction

New runtime plan v2 separates sanitizer test_parallel=min(2,parallel) from unchanged build parallel4. Historical v1 reconstructs exactly with its original parallelism. The runtime executor and semantic validator both bind the actual CTest argument. New fallback request/evidence v4 uses parallel2 with unchanged case120/wall480; published v1/v2 retain original limits and scheduling. Full source/context/argv, plan/request digests and native-output checks remain enforced.

No timeout, CPU/RAM/disk ceiling, test/context population, sanitizer/fuzz requirement, tool recipe, source, score or approval gate is relaxed. The original runtime-scope fixture and isolated diagnostic are unchanged. The earlier rejected450/240-second extension and its fixture are not included, retried or rerouted; fallback v3 remains rejected. The workflow change only adds the new tests to the existing contract checks.

## Verification and review

Fresh final13-module selection:370 distinct passes, zero failures/errors/skips, including30 new cases; narrower counts overlap. Cross-version corruption still rejects even after recomputing a plan digest because native CTest argv differs. Malformed schemas, altered limits, failure retention, complete simulated required outputs and original evidence compatibility are covered. Existing current-version/parallel expectations were updated; historical assertions remain in dedicated tests.

Initial RED and intermediate failures are retained, including missing-new-API failures that are not described as behavioral REDs. A broad combined invocation exceeded the command limit without terminal JUnit; no passing claim is made for it. Local scoped Python3.13.5/pytest9.0.2 is not pinned hosted parity and has no Docker. The connected-agent supplied-code critique withdrew an unsupported replay concern after checking exact hashes/argv/tamper tests; no concrete defect remained in that bounded delta. It is not full independent PR approval. Exact hashes, commands and scope: docs/evidence/pr1644-contention-scheduling-20260926/verification.json.

## Required completion

Qualify this exact candidate through existing owned controls and the complete frozen native campaign, preserving all failures and checking sanitizer/static/fuzz populations and instrumentation. Successful isolated cases and local tests are not complete qualification. C5/C7 remain unproven for the new candidate; prior full failures remain failures. C1/C6 retain only their earlier scoped evidence; all remaining incomplete C0–C19 rows stay unproven.

PR1645 has green ordinary checks, not actual failed-input replay or complete applicable review. Preserve its authenticated-input access boundary; no production-record diagnostic is rerouted. Complete required review and actual-input report verification, then reconcile the final release evidence. Production-only acceptance is deferred by the owner's shipping hold, not passed. No merge, deployment, database/assessment mutation, report approval or delivery occurs in this candidate.


## Collection correction publication — full run terminal, target failure retained

The containing commit publishes the recovered collection correction on the existing PR1644 branch, based on 0c8ed575. PR1645 remains97666911. Preserve the existing no-shipping hold and all prior requirements. The earlier verification.json records the original unpublished preparation; publication-verification.json records fresh full-checkout verification.

Full run36207402575 is now terminal FAILURE. Artifact10896373460 is20,800,345bytes, SHA256d460f23b62fc54474a5fb2aa0880f54b7b1d71d009af3b06c16c87632d533286. Data-only reconstruction verifies baseline377/377, compiler475/475, functional6/6, ASan377/377 and static475/475. UBSan executed377 tests with376passing; net_tests reports a null-pointer nonnull-argument diagnostic at src/streams.cpp:99:24 on the unchanged frozen Bitcoin revision. This is not a timeout or proof of exploitability. Fuzz replay/campaign did not execute. All original failures and production_qualified=false remain.

The evidencev4 correction admits independent later collection only after a full returned CTest population, no skip or timeout, exit8 and explicit Failed records. It preserves the target failure and complete=false; it cannot turn the run into successful qualification. Historical evidencev1/v2/v3 keeps its original grammar. Missing/invalid/timed-out execution still aborts. No assessed source, case/suite/aggregate timeout, population, tool/image, CPU/memory limit, approval or qualification gate changes. The full workflow only adds the new regression module to contract tests.

Final affected tests:311distinct passes, including22new cases. The initial14-case run had10failures/4passes, of which three directly reproduce lost later collection and seven stop at that missing-suffix prerequisite. The existing current-emitter schema assertion is the sole modified old assertion. The exact real native summary is byte-identical before/after; its failure remains failed. Actual UBSan data qualifies for later collection while the historical ASan timeout does not. No new native execution is claimed.

The earlier preparation session could not publish. This continuation recovered the exact patch, verified every code/test/workflow hash and preimage, and applied it to the full repository. Fresh exact workflow contract selection: 1319 passed, 1 skipped (local CMake toolchain unavailable), 0 failures, exit 0, with pinned requirements on Python 3.12.14. The original native archive hash was verified and its reconstructed summary is byte-identical to the earlier preimage result. The real retained UBSan failure admits later collection without changing its failed outcome. Full hosted/native verification remains required; these checks are not native fuzz execution or independent review. No denied timeout-extension or production-record diagnostic was retried/rerouted. Required next work is exact-candidate native collection including fuzz, truthful source-diagnostic disposition and complete applicable review, actual failed self-assessment inputs/replay, and final shared-ledger integration. Green qualification must not be fabricated from these local tests or by clearing the real target failure. No merge, deployment, production/data/assessment change, or approval was performed.
