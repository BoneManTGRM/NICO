# PR1641 continuation — measured compiler-budget repair

Continue PR #1641 on `feat/cpp-full-project-capacity`. Parent `2195a416ba3750b3269f366a27083038f7957da2`, tree `1322ec1fdd7ee21abc64283a5986b77d7a52e727`; main/base `faaa10b037eb58e4175561b96dadf0d929764df4`. The original C0-C19 contract and stronger owner requirements remain binding. Record publication SHA in the PR, not a self-hash commit. No full-assessment, review, merge, production or approval claim.

## First native failure established

Integration35945262906 / Bitcoin job107463662238 failed. Artifact10787164500 is12,104,412 bytes, ZIP SHA256 `82f966b8c9b3336a24fe7f2c4e4f891c3a4f3547b7ff499519d93ff21b0bb253`; source artifact10785944892 is4,450,088 bytes, SHA256 `af3eeacf79f502e4180e4d5798ca31738a9ea995c26a5079a19116144c5676c5`. Both downloaded archives were hash-verified. The source CI merge `1a226696c9a442df8ecb37a689b8c8d161d10db9` is not a production merge.

Actual a561 stages: full build854,352ms;377 discovered/executed/passed native tests, zero skipped, test295,671ms;121 generated files/32,033,843 bytes verified. All475 compiler contexts were attempted but only474 completed. Last index474 exited124/timed_out=true after4,628ms because the shared540-second deadline was nearly exhausted. Native compiler total540,022ms; no output truncation. Its retained artifact is34,385,267 bytes, SHA256 `2c14c51fec91f0de855889de167a2eb34a44812f3f139cd7e0ebb4288db9063f`. Probe duration1,716,180ms, memory peak9,034,354,688 bytes, boundary/scratch/cleanup verified. Error `worker_configuration_probe_compiler_incomplete`. Static stage and static result are null: this was NOT a Cppcheck execution failure or a Bitcoin build failure.

Native owned artifact10786249375 is1,643,741 bytes, SHA256 `c7ced4177287ee56a629fc43f0ff8ff8b23af110039035a633627d3a9fd4f997`. The real clean and diagnostic controls each completed four compiler/static contexts; clean had zero findings, diagnostic one uninitvar and one unassignedVariable generated-source candidate. These native controls used the parent normal check level, not the now-required exhaustive level. Unused header remained unvisited. Linked-header negative failed before compiler/static as required. All controls retained cleanup and expected outcome. This is owned qualification, not production acceptance.

## Concurrent correction preserved

The publication recheck found2195a416 on the same branch before any ref mutation. Its static depth is exhaustive, not normal; its600-second stage rejects results returned, retained or validated at/after the deadline while retaining bytes and cleanup. Preserve all three application changes and both test additions. The recovered2195 source/test blobs were reconstructed byte-exactly: static fecf6165b850531c19f57671690e44b0e42baa7e; static tests5c60d9df7389acab7d8afaf9dc826dd14e62bd96; stage tests8691041c775af7accdcf01d2f22276b65937dcf6. Only compiler-budget reconstruction is merged into the overlapping static module; both test files remain identical to2195. Earlier uploaded conflicting blobs remain unreferenced, not published. No concurrent commit is reset.

The2195 recorded seven RED cases, ten repaired passes and196 affected passes are retained predecessor evidence, not independent review. Fresh integrated budget/compiler/static/stage/snapshot regression group now passes184 tests in3.14s, exit0, including all14 new budget tests and nine final-deadline cases. Old175/14 counts overlap and are not additive. The restored exhaustive-depth selection invalidates the earlier normal-level analyzer qualification, not the unchanged build/test/snapshot evidence. Actual exhaustive owned and Bitcoin completion still require hosted native proof.

The2195 checkpoint records a561 NICO CI35945262901/backend107461697467 failing the unchanged watchdog test at second_started.wait(1.5), with11,598 passed,1 failed,136 skipped; a focused four-test pass does not establish the hosted root cause. Preserve that unresolved mandatory-check observation. No watchdog assertion, timeout or production code is changed by this compiler repair.

## Bounded correction, not target reduction

Add opt-in compiler request/evidence v2 with600 seconds aggregate, retaining90 seconds/context and four concurrent compilers. Legacy v1 defaults remain540/90/4 and old receipts retain their identities. The controller forwards the selected version; the embedded collector and validator enforce it; static preparation reconstructs and validates the matching compiler version. Existing owned and Bitcoin qualification commands opt in before large execution. No required context, option, generated member or test is removed.

Measured prior cbecc compiler runtime484,825ms passed all475; a561 needed more than540 seconds with the same frozen population. Current measured noncompiler remainder is approximately1,176,158ms; adding600 seconds gives1,776,158ms inside the unchanged1,800-second executor. This arithmetic motivates bounded headroom, not a native sufficiency guarantee. Outer controller1810 seconds, static600/610 seconds, aggregate2400/2420 seconds, existing50-minute hosted job,4 CPU/12 GiB/no swap/256 PIDs/9 GiB scratch all remain unchanged. No new privilege, paid plan or resource class.

Protected risks verified: receipt relabeling, lost/repeated contexts, unlimited or coerced budgets, and a last-context timeout falsely credited as complete. Exact a561 native bytes still validate as474/475 under v1 and reject under a forged v2 binding. Both versions preserve identical context membership/commands; only policy identity and bounded scheduling change. Snapshot/source/build success remains retained; dependent compiler/static qualification is pending the new native result.

## Fresh verification

Initial missing versioned compiler behavior:11 RED failures. Smallest implementation:11 GREEN. Missing probe/script/workflow connections:3 RED and11 passing. Repaired exact suite:14 passed, exit0. Affected group A:175 passed in4.62s, exit0; disjoint group B:160 passed in20.58s, exit0. The14 are included in175, not additive. Additional disjoint existing groups66/81/17 pass with terminal exits. Larger local groups hit35s/30s command limits and do not establish a completed aggregate pass; their subsets and logs remain explicit. Hosted complete regression gate remains required.

All changed Python ASTs and13 workflow shell blocks parse; git diff --check passes. Workflow job dependencies, permissions, concurrency, resource/time bounds, source/tool pins and artifact handling are unchanged apart from registering the new test and selecting compiler v2. No new local Docker/Bitcoin execution or independent review is claimed.

## C0-C19 current evidence crosswalk

| Predicate | State | Current scope |
|---|---|---|
| C0 | UNPROVEN | Source/control/baseline recovered; complete runtime contract/budgets still unfinished. |
| C1 | PASS | Frozen inventory3,248 entries/3,031 materialized files/49,729,651 bytes reverified. |
| C2 | UNPROVEN | Native baseline and owned static boundaries pass; complete combined scope pending. |
| C3 | UNPROVEN | Existing worker authority subproof retained; final full-workload binding pending. |
| C4 | UNPROVEN | Durable subproof retained; normal-intake complete dispatch/ingestion pending. |
| C5 | UNPROVEN | Parent normal-level owned static4/4 controls pass; exhaustive-level owned/Bitcoin qualification pending. Bitcoin static did not execute in a561. |
| C6 | FAIL | Latest a561 compiler474/475 timed out; v2 correction awaits native qualification. Prior cbecc475/475 remains historical proof. |
| C7 | UNPROVEN |377 native tests pass; required functional/integration/sanitizer/fuzz scope unfinished. |
| C8 | UNPROVEN | Full native-to-canonical and cross-format identity reconciliation pending. |
| C9 | UNPROVEN | Current partial population accurately retained; complete static/runtime populations pending. |
| C10 | UNPROVEN | Scoring unchanged; final valid-input/assurance projection pending. |
| C11 | UNPROVEN | Baseline measured; v2 plus complete combined workload not yet qualified. |
| C12 | UNPROVEN | a561 native owned controls pass at normal depth; v2/exhaustive and final supported-language regression proof pending. |
| C13 | UNPROVEN | No actual full-supported Bitcoin Comprehensive report. |
| C14 | UNPROVEN | Final bilingual/mobile/progress/recovery evidence pending. |
| C15 | UNPROVEN | Approval/history unchanged; final affected-surface verification pending. |
| C16 | UNPROVEN | New final CI and genuinely independent complete review pending. |
| C17 | UNPROVEN | PR unmerged; no new serving production release. |
| C18 | UNPROVEN | No normal-intake production Bitcoin run of completed capability. |
| C19 | UNPROVEN | Native artifacts retained; final reports/hashes/repeated retrieval pending. |

Independent review request5802036311 received reply5802038248 reporting exhausted allowance. No independent review occurred; do not retry unchanged requests, buy credits, switch accounts or waive review. This is separate from permitted implementation. No operator approval or client-delivery authorization is performed. Historical Bitcoin revision `0e9018e8b65611b0769545e177110e4b7fc51244` / run `comprun_7cc47a5a81695fa452354479ea23b422` and unrelated Railway staged changes remain untouched.

## EXACT NEXT ACTION

Publish the tested bounded repair atomically after rechecking the current branch, without force or duplicate manual execution. Inspect automatically triggered owned v2 controls, full contract gate and the475-context Bitcoin compiler/static outcome. Reconstruct retained native bytes and diagnose the first actual failing layer without target removal or blind retry. While execution runs, advance remaining permitted runtime and durable canonical/report integration. Then independent complete review, final checks, merge/deploy, authoritative Vercel/Railway/worker serving mappings, actual authorized production owned/Bitcoin runs and English/es-MX draft artifacts with repeated retrieval. Do not stop or declare SHIPPED at a component gate.

Frozen qualification target remains `bitcoin/bitcoin@bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`, database `fc89aa69b2a369417cbff01d2784225bd23547827b1f7fd946669f919526aa1b`. Linux Debug wallet/tests/IPC/embedded data stay enabled; GUI/benchmarks/ZeroMQ/other-platform variants stay outside the previously frozen baseline.

## Immutable predecessor

Immediate preceding checkpoint: `2195a416ba3750b3269f366a27083038f7957da2:NICO-Ship-Checkpoint.md`, blob `8cb1e10d80334006cd4e0fb11b7257faa1322b3f`. Its a561/cbecc/fd1/254/b609/d236/a10/abb/1ebc chain preserves original C0-C19, merged PR1627, exact security dispositions, authorization/worker/database/production and historical approval evidence. This remains the only active mission ledger.
