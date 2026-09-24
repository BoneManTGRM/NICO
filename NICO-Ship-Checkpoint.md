# PR1641 continuation — compiler environment qualified; static evidence transport compacted

Continue existing PR #1641 / `feat/cpp-full-project-capacity`. Parent `e11822933556cc42b1acd5b58b57f2d85a00591e`, tree `632abd91d28fdebff5422833eae282cbbebd6923`; observed main/base `faaa10b037eb58e4175561b96dadf0d929764df4`. Recheck live refs before non-force publication; preserve concurrent work. Record the containing commit in the PR, not a self-hash commit. Local source-export Git metadata is an empty detached test fixture with no remotes and MUST NOT be pushed. The original NICO-CPP-Bitcoin-Execution-Prompt.md and stronger C0-C19 contract remain binding. This is not merge readiness, independent review, deployment or a production report.

## Recovered defect and actual implementation

Parent e118 restored the exact executable static module after two commits replaced its476 lines with `placeholder` and then `see-local-file`. The broken source produced39 failures/2 passes; the identical restored test command passed41, and the broader affected set125. Preserve this non-force repair and its immutable checkpoint, not either placeholder.

The remaining static setup defect is now addressed by a generic producer AND its consumers, not another disconnected schema. The new environment collector runs inside the existing disposable static sandbox after baseline destruction and generated-input restoration. It queries pinned GCC14.2.0 on `/dev/null`, retaining language/standard/scalar defines/undefines and native version, predefine and search-root bytes. It does not execute source or repository scripts. Every result binds to the exact image/compiler receipt and complete context population. Identical scalar queries may share native observations; repeated translation-unit configurations remain distinct.

Only compiler-reported toolchain dependencies are read from the immutable `/usr` tree. Resolved paths stay within `/usr`; component reads use no-follow protections; original bytes/digests are retained and projected into the private analyst tree. Pinned Cppcheck2.17.1 std/posix/gnu/boost model hashes are verified. Named public C/C++ and POSIX headers use the upstream library models rather than attempting to parse their implementation headers. Such native missing-include messages are retained as `modeled_inputs` only where the actual compiler resolved that exact public header for that context. They are explicitly NOT analyzer-visited headers. Missing custom, Boost, Cap'n Proto, unbound, malformed, critical and no-op-checker evidence still prevents completion; no suppression switch or target removal is introduced.

The existing static producer and validator now consume the observed environment, preserve supplied include order, project supported `-isystem` inputs to the pinned importer's usable include representation, and verify dependency/predefine/model bytes before and after analysis. Legacy v1 evidence remains reconstructible. New environment-bound static request/evidence/stage v2 records contain hashes, modeled-input disclosures, native findings and separate compiler/analyzer populations.

The configuration probe and both existing qualification scripts forward the same explicit `--compiler-environment` flag. The existing workflow enables it for owned and frozen large qualification, with the owned stage still first. Owned fixtures now exercise compiler predefines, public library models, implicit Boost headers and a generated SYSTEM include, along with clean/diagnostic/repeated/generated/link-negative controls.

A final real-storage test exposed an omitted allowed artifact type: the actual immutable sink rejected `project-static-environment`, while a mocked sink had accepted it. Recorded RED1 failure; identical GREEN1 pass after adding exactly that known key. Existing size/path/atomic/no-overwrite behavior remains. The test verifies real retained bytes, idempotence and corrupt-existing-file rejection. This was repaired before publication.


## Latest hosted Bitcoin failure and bounded repair

Candidate `8f7f1248c2b5832eb9ec004429556ff8a1df1ef6` passed hosted contract regressions and owned-project integration in run36013349958. Frozen Bitcoin job107683778968 retained artifact10816400065 (ZIP SHA256 `c3eb99d9bfee3f4992414cfb6e8985cf1184559c5205fe97d0954db3effc770b`). The environment producer completed475 contexts /12 queries /1439 headers /16,624,324 retained header bytes, and compiler-v2 again completed all475 contexts. The static stage entered real analysis and ran for227,017ms with7,592,583,168-byte peak memory; isolation and cleanup passed. Its first failure is `worker_project_static_output_limit`: the monolithic native JSON exceeded the existing48MiB evidence transport/storage cap. This is not a build, test, compiler-environment, analyzer-timeout, or dropped-target failure.

The repair keeps the48MiB outer evidence and immutable artifact caps unchanged. Environment-bound v2 records now zlib-compress each retained Cppcheck XML member before base64 transport while preserving the SHA256 of the exact uncompressed native XML. The validator accepts historical uncompressed v2 evidence and new compact records, performs bounded decompression (1MiB native XML /2MiB stored-member caps), verifies stream termination/no trailing data and the original raw digest, then applies the unchanged parser/completion rules. Legacy v1 evidence stays byte-compatible. No finding, limitation, invocation, context, analyzer depth, timeout, resource class, model input or approval rule is removed. This is bounded representation compaction, not an evidence reduction.

Focused static/environment/stage tests:91 passed. Broader affected static/environment/native-preprocessing/full-project set:196 passed, zero failures/errors/skips. A subsequent unchanged all-workflow local invocation exceeded the local command window after partial progress and is not credited; candidate hosted contract regressions remain mandatory. Two new cases verify compact XML round-trip and truncated compressed evidence rejection.


## Latest qualification-summary budget failure and bounded projection

Candidate `50e501e1b8cb50bd3b1a57b6babeba8a474f02ff` passed hosted contract regressions and owned-project integration in run36024277039. Frozen Bitcoin job107720070151 retained artifact10819979024 (ZIP SHA256 `a4f66b72fb2733df5bc672342bb63c5a58d3686fd3069af591898902cace708e`). The lossless XML compaction cleared the prior48MiB static-output boundary: the static native artifact is3,878,970 bytes and the stage completed its native evidence retention. The next failure is the engineering qualification controller's separate16MiB `receipt.json` budget while saving the fully validated static populations. The preceding retained receipt is9,788,833 bytes and the raw immutable native artifacts remain separately retained. This is not a Bitcoin build/test/compiler/static-execution failure and does not justify increasing either evidence cap.

The correction keeps the16MiB qualification-receipt cap unchanged. `qualification_probe_receipt` now projects only large reconstructible static populations (`required_contexts`, `attempted_contexts`, `analyzed_contexts`, findings, limitations and modeled inputs) to exact count + canonical SHA256 pairs in the engineering receipt. The static native artifact reference, native/compiler/environment hashes, completion flags, model limits and all scalar assurance/review fields remain. The live probe object is not mutated, and `project_static_stage.analysis` receives the same hash-bound summary only in the qualification receipt. Exact validated populations remain reconstructible from the immutable native artifact and candidate code; no finding or limitation is deleted from native evidence.

Recorded RED: the new receipt-projection test failed because no projection existed. Identical focused GREEN passes. The complete affected configuration/static/static-stage/environment selection passes108 tests, zero failures/errors/skips. Hosted contract regression remains required on the published candidate.


## Compiler-resolved Boost dependency modeling

The retained `50e501e1` Bitcoin native static artifact contains475 native Cppcheck records with zero execution timeout/truncation. Direct reconstruction identified241 contexts with critical analyzer diagnostics:153 `preprocessorErrorDirective` messages from installed Boost integer-traits implementation headers,87 `syntaxError` diagnostics (85 at `/usr/include/boost/multi_index/detail/bucket_array.hpp:82`, two in another Boost internal header), and one `internalError` in first-party `src/coins.cpp`. The first two populations are caused by feeding installed third-party Boost implementation headers to Cppcheck despite already loading the pinned upstream `boost.cfg`; they are not source findings and cannot earn completion.

The generic environment policy now models only compiler-resolved system Boost paths (`boost/...` under an approved compiler-native include root) with the existing hash-pinned Boost library model. Their native dependency bytes/hashes remain retained in environment evidence and any native missing-include message remains an explicit `modeled_input` bound to the compiler-resolved path. Arbitrary absent Boost names, vendor/application include roots, custom dependencies and Cap'n Proto remain blocking. Actual Boost implementation headers are no longer projected into the analyzer workspace, avoiding parser failures in third-party internals without suppressing a diagnostic or changing first-party target coverage. The environment `model_policy` advances to `gcc14-unix64-public-c-cpp20-posix-boost-upstream-models-v2`.

Recorded RED: two focused model-policy assertions failed against the prior producer. Identical focused GREEN:2 passed. Final affected environment/static/preprocessing/stage/configuration selection:154 passed, zero failures/errors/skips. A new negative case proves `boost/not-compiler-resolved.hpp` remains a blocking missing input. The one retained first-party Cppcheck `internalError` remains unresolved and must not receive completion credit; qualify the new model first, then repair or supplement that exact context if it persists.

## Frozen limits and invalidation

Environment:30 seconds inside the unchanged600-second static stage;5 seconds/query;128 distinct queries;4096 toolchain headers;2MiB/member and32MiB total header capture;16MiB request and48MiB output caps. Existing1800-second baseline parent,600-second compiler-v2/90-second cases/four workers,540-second analyzer/90-second cases/four workers,600/610 static boundary,2400/2420 aggregate envelope,50-minute CI job and4CPU/12GiB/no-swap/256PID/9GiB scratch remain unchanged. No new runner, service, privilege, paid plan, manual workflow dispatch or production activation.

Changed static environment inputs invalidate dependent static qualification, not unchanged original inventory/build/tests/compiler bytes. Correctly configured complete Bitcoin analysis may require further measured scheduling work; failed-preprocessing timing is not capacity proof. No blind threshold increase or reduced depth.

## Verification actually completed

Initial producer and consumer RED cases, actual native layout counterexample and qualification-wiring RED/GREEN remain retained. The real-artifact-sink correction was also reproduced before repair. Final updated workflow contract population:35 files /933 distinct cases, collected and run in ten disjoint bounded groups, all exit0; zero failures/errors/skips. Exact JUnit membership equals collection with no duplicates or omissions. Membership SHA256 `e8471801cd3a5b9a3759684b5c6e2ea89ecf30e51ceb6c52e99b51d6b4d2b68a`. Earlier932/125/104 counts overlap and are not additional coverage.

One earlier group failed two Git metadata lookups because the archive has no Git directory; only a detached empty local fixture was added and the unchanged tests passed. One multi-group outer tool invocation was interrupted after group1; the missing group2 was run unchanged alone. Partial output is not credited. Local dependencies differ from hosted pins. Python ASTs, all three embedded programs,14 shell blocks, unchanged workflow resource/pin/order comparisons and patch whitespace/application checks pass. This is not full-backend, Docker, independent review or production proof.

The real local native producer executed three owned original/repeated/generated contexts with GCC14.2.0 and the exact retained Cppcheck2.17.1 executable/models. All3 compiler and static contexts completed; two intended generated-source candidates (`uninitvar`, `unassignedVariable`) and four modeled public-header disclosures were retained. Environment capture had3 queries /81 headers /1,411,116 bytes. It used UID1001,2GiB address-space,60 CPU seconds and48MiB file bounds, temporary tool aliases and cleanup. This was NOT the hosted full worker image, Docker boundary, Bitcoin, production intake or independent review. The new four-context CMake controls still need hosted execution.

Reconstructing the existing frozen Bitcoin compiler receipt yields475 environment contexts /12 unique compiler queries /1439 toolchain headers,13,056,019-byte request under the existing16MiB limit, SHA256 `a8e9f3522a71c77f9de9cd98b50756333890f77e1e6e4f37d6d328d6de60d88c`. This is request validation only, not native new-policy execution. Evidence: `docs/evidence/pr1641-compiler-environment-20260924/verification.json` and `test-results.log`; bulky local XML/native artifacts remain in the conversation evidence bundle. Every uploaded source blob must match its recorded verified bytes.

## Retained Bitcoin baseline and failed static evidence

Frozen Bitcoin `bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`, database `fc89aa69b2a369417cbff01d2784225bd23547827b1f7fd946669f919526aa1b`. Linux Debug wallet/tests/IPC/embedded data remain enabled; GUI/benchmarks/ZeroMQ/other platforms remain outside the frozen baseline, not removed after failure.

Retain run35978926706/job107568329757/artifact10800637897:3,248 inventory entries /3,031 source files /49,729,651 bytes; build passed;377 native tests executed/passed, zero skipped;121 generated members /32,033,843 raw bytes;475/475 compiler-v2 contexts;406 original and92 generated compiler-visited headers. Static attempted475 but corrected interpretation gives2 completed and167 unreviewed candidates;429 preprocessing errors are limitations, not code-risk findings. ZIP SHA256 `80c977ed121797428e6547bffcacf6b7551978074e9e084596330b83bcd8ea69`; static native `b46607d23bd87a969c772dc071d54d9c88e97db37f50b119bf787d14682ea65a`. Baseline1,740,770ms, failed static29,337ms, aggregate1,770,235ms; memory peaks8,851,746,816 and4,541,882,368 bytes. Actual isolation/cleanup retained. No historical bytes/report/approval is rewritten.

## C0-C19 whole-row status

| Predicate | Status | Scope / remaining evidence |
| --- | --- | --- |
| C0 | UNPROVEN | Current source/authority/target recovered; full runtime scope and aggregate production budgets remain. |
| C1 | PASS | Complete frozen inventory/acquisition retained; production revalidation belongs to C18. |
| C2 | UNPROVEN | Prior isolated boundaries retained; new complete workload/production enforcement remains. |
| C3 | UNPROVEN | Full production receipt identity/authority binding remains. |
| C4 | FAIL | Full configure-first project evidence still not connected through normal durable production completion. |
| C5 | UNPROVEN | New native owned3/3 passes; hosted owned and all475 frozen Bitcoin contexts still require qualification. |
| C6 | PASS | Retained baseline/generated/compiler/header evidence unchanged. |
| C7 | UNPROVEN |377 baseline tests pass; declared functional/integration/sanitizer/fuzz scope remains. |
| C8 | UNPROVEN | Environment/findings bindings implemented; actual canonical/report reconciliation remains. |
| C9 | UNPROVEN | No header-visit or modeled-input conflation; full static/runtime/report population acceptance remains. |
| C10 | UNPROVEN | Scoring unchanged; actual final report assurance projections remain. |
| C11 | UNPROVEN | Complete correctly configured Bitcoin static/runtime resource qualification remains. |
| C12 | UNPROVEN |933 local cases pass; final hosted controls and supported-language qualification remain. |
| C13 | UNPROVEN | Actual full-supported production Bitcoin report absent. |
| C14 | UNPROVEN | New production bilingual/mobile/progress/recovery acceptance absent. |
| C15 | UNPROVEN | Human/history controls untouched; exact-edition eligible one-action acceptance remains. |
| C16 | FAIL | Complete native qualification, final required checks and independent review remain. |
| C17 | FAIL | PR unmerged; no new production serving release. |
| C18 | FAIL | No normal-intake production Bitcoin run exercising completed capability. |
| C19 | UNPROVEN | Final bilingual artifacts/hashes/repeated retrieval absent. |

Prior Codex review request5802036311/reply5802038248 exhausted allowance; do not retry unchanged requests, buy credits, switch accounts, waive review or call author verification independent. No human approval or delivery authorization performed. The older rejected Bitcoin build/config/test/sanitizer/fuzz discovery operation must not be evaded; establish its exact supported resolution separately from permitted generic implementation. No new denial or universal support-ticket block is claimed. Existing GitHub publication works.

EXACT NEXT ACTION: publish the compiler-resolved Boost model as a non-force descendant after a fresh live-head check, then inspect the queued hosted owned and frozen475-context Bitcoin qualification. Preserve the next actual failure without increasing the16MiB receipt cap, dropping populations, or lowering depth. Continue the existing durable worker/canonical/report integration and permitted runtime work while hosted qualification runs. Obtain independent complete review and all pre-merge gates, then merge/deploy through existing platforms and prove normal owned then authorized Bitcoin intake with actual English/es-MX artifacts and protected approval/retrieval. No SHIPPED claim before every mandatory row passes.

## Immutable continuity

Parent `e11822933556cc42b1acd5b58b57f2d85a00591e:NICO-Ship-Checkpoint.md` records exact placeholder recovery. Its95f/533d/3652/2195/a561/cbecc/fd1/254/b609/d236/a10/abb/1ebc chain preserves original C0-C19, merged PR1627, native successes/failures, worker/database/serving proofs and historical approvals. Bitcoin historical revision0e9018e8b65611b0769545e177110e4b7fc51244 / runcomprun_7cc47a5a81695fa452354479ea23b422 remain unchanged. This file is the sole active ledger.
