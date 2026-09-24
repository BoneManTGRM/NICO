# PR1641 continuation — native static failure established; truthful diagnostics repaired

Continue existing PR #1641, branch `feat/cpp-full-project-capacity`. This candidate descends from `533d8d5ea833ad4b897cff8be734c1ce831175fe`, tree `9c64b8a439e7a126ffd0dea6f9c5ac4d7388613f`; observed main/base `faaa10b037eb58e4175561b96dadf0d929764df4`. Recheck live refs before any non-force publication. Never push the locally initialized source-export test fixture. Record publication identity in the PR, not a self-hash commit.

The original NICO-CPP-Bitcoin-Execution-Prompt.md and stronger current C0-C19 requirements remain binding. This is not a passing full assessment, independent review, merge, release, production execution or human approval. No security or approval control is waived.

## Current primary native evidence

The screenshot's failed check is integration run35978926706, Bitcoin job107568329757. Artifact10800637897 contains the actual terminal native receipt and immutable generated/compiler/static outputs. Its ZIP is12,837,611 bytes, SHA256 `80c977ed121797428e6547bffcacf6b7551978074e9e084596330b83bcd8ea69`. Source artifact10799650915 is4,454,479 bytes, SHA256 `9f8f5f70829dd1b581cc53283c75b48a4bf3453f3880af482d3722adef631251`. The source export's CI merge `d7739f3cf010237a36464067e373588a403271bc` is not a production merge; its tree matches the parent tree above.

Reconstructed the source inventory, every captured generated-file digest, compilation contexts, compiler native proof, static request/output bindings, native discovery and complete JUnit population from those bytes:

- Frozen Bitcoin `bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`.
- Complete3,248 inventory entries,3,031 materialized files,49,729,651 source bytes.121 generated files,32,033,843 raw captured bytes.
- Build passed.377 discovered=executed=passed native tests; zero skipped. This is baseline proof, not the remaining functional/sanitizer/fuzz scope.
- Compiler v2 completed all475 required/attempted contexts;406 original and92 generated compiler-visited headers. Native compiler artifact SHA256 `15d92235ae5bd2880b1d3239d5aa837e665e5732f6b15a737a01d8dcc0aca69c`.
- Static Cppcheck2.17.1 actually attempted475 contexts and returned bounded output with exit0, no timeout or truncation. It did not complete preprocessing:435 critical checker reports,429 preprocessor-error directives,4,414 missing-system-include messages and6 unknown-macro diagnostics. This is not another compiler timeout or a Bitcoin build failure.
- Principal preprocessing messages are397 missing compiler-attribute-environment errors and32 missing Cap'n Proto header-environment errors. Imported compiler commands lack the compiler's implicit predefines/search environment; no repository-specific exception or suppression was added.
- Baseline/capture/compiler1,740,770ms; static sandbox29,337ms; aggregate1,770,235ms. Peaks8,851,746,816 and4,541,882,368 bytes respectively. Both isolation boundaries and cleanup validated. These timings describe failed analysis, not qualified full-analysis performance.

The baseline scope remains Linux Debug wallet/tests/IPC/embedded data ON; GUI, benchmarks, ZeroMQ and other-platform variants remain outside the previously frozen scope. Database `fc89aa69b2a369417cbff01d2784225bd23547827b1f7fd946669f919526aa1b` and every required/repeated context remain unchanged.

## Earliest incorrect result layer repaired

The shared native parser previously classified `preprocessorErrorDirective` as a source code-risk candidate and treated every `checkersReport` as harmless, including critical failures. This could grant completion in the per-context, configured-worker, full-project-worker, standalone-worker and standalone-scanner consumers.

The parser now retains preprocessor failures as limitations, preserving the native rule/message/location. Only a positive well-formed checker inventory is harmless; critical, zero-checker or malformed inventories also produce a derived `native_checkers_unproven` limitation with the original native rule identified. Existing consumers already reject that limitation. Genuine finding-bearing execution remains eligible. No raw evidence or prior stored report is rewritten.

Replaying the unchanged current native artifact under the correction yields2 completed static contexts rather than the stored110, and167 review candidates rather than596. The429 removed code-risk entries are tool preprocessing failures, now retained as limitations. The other167 candidates are not independently verified vulnerabilities. Static artifact SHA256 remains `b46607d23bd87a969c772dc071d54d9c88e97db37f50b119bf787d14682ea65a`.

This corrects truth, not the unresolved compiler-predefine/include-model setup. Do not mark the failed integration green on the strength of parser tests.

## Verification and bounded native reproduction support

New synthetic regressions exercise all five real consuming seams plus positive checker inventory and genuine diagnostic controls. Corrected baseline RED16 failed/4 passed; repaired GREEN20 passed. An initial new-test field-name mistake was corrected and RED repeated; no production field or existing assertion was weakened. The existing inventory fixture now uses the pinned tool's real positive message rather than fabricated generic text.

Complete33-file workflow selection plus five affected scanner/receipt/configuration/runtime files:1,042 unique cases passed, zero failures/errors/skips. Seventy-seven disjoint terminal groups reconcile exactly to the collected population. An interrupted larger group is retained as incomplete, not counted; the same required cases were split without omissions. Focused20/61 and historical875 counts overlap and are not added. Local dependencies differ from the pinned hosted environment, so final hosted regression remains mandatory.

Evidence index: `docs/evidence/pr1641-native-preprocessing-20260924/verification.json` and `test-results.log`. Full local XML/logs and reconstruction scripts are preserved in the conversation evidence archive. Existing native evidence remains in the authoritative GitHub artifact above.

The existing owned integration job now retains the exact pinned Cppcheck executable/models from a never-started image container for bounded owned diagnostic reproduction. It copies no assessed source, mounts or secrets, checks64MiB aggregate/32MiB executable bounds, hashes files, and removes the container with a trap. No extra workflow dispatch, executable target workload, runner, privilege or paid plan is introduced. Hosted capture itself still requires verification. Existing owned controls continue before Bitcoin.

All compiler v2 allocations, parent/static deadline repairs, actual execution limits, resource class, exhaustive depth and required target populations are byte-preserved. The local container has no Docker or installed pinned Cppcheck; do not claim local native analyzer qualification. Native execution continues on the existing CI worker, not the serving app or a credential-bearing controller.

## Whole-row C0-C19 status

| Predicate | Status | Evidence and remaining scope |
| --- | --- | --- |
| C0 | UNPROVEN | Current source/authority/target recovered; complete runtime groups and aggregate production qualification remain. |
| C1 | PASS | Complete frozen inventory/acquisition reconciled from artifact10800637897. |
| C2 | UNPROVEN | Actual baseline/static isolation and cleanup pass; complete workload/production enforcement remains. |
| C3 | UNPROVEN | Prior identities retained; full production receipt binding remains. |
| C4 | FAIL | Full project-wide evidence is not yet connected through normal durable production completion. |
| C5 | FAIL |475 static attempts but incomplete preprocessing; corrected interpretation completes only2 contexts. |
| C6 | PASS | Current v2 baseline,121 generated members,475 compiler contexts and compiler header populations verified. |
| C7 | UNPROVEN |377 baseline native tests pass; declared integration/sanitizer/fuzz scope remains. |
| C8 | UNPROVEN | Native failures/candidates corrected; actual canonical/report cross-format acceptance remains. |
| C9 | UNPROVEN | Current baseline/compiler membership passes; static failures explicit; complete runtime/report reconciliation remains. |
| C10 | UNPROVEN | No scoring redesign; actual new report inputs/projections remain unverified. |
| C11 | UNPROVEN | Partial-workload measurements retained; correctly configured full analysis/runtime not qualified. |
| C12 | UNPROVEN |1,042 local cases pass; new pinned hosted/native controls still required. |
| C13 | UNPROVEN | No complete-scope production Bitcoin structured report or PDF. |
| C14 | UNPROVEN | No new production bilingual/mobile/progress/recovery acceptance. |
| C15 | UNPROVEN | Human/history controls untouched; exact-edition eligible one-action acceptance remains. |
| C16 | FAIL | Full native qualification fails; independent complete review and final candidate checks remain. |
| C17 | FAIL | PR unmerged; no new merged serving identities. |
| C18 | FAIL | No actual normal-intake production Bitcoin run exercising the completed capability. |
| C19 | UNPROVEN | Native/local evidence retained; final bilingual artifacts and repeated retrieval absent. |

Prior Codex review request5802036311/reply5802038248 exhausted its allowance. No independent review is claimed. Do not retry unchanged requests, buy credits, switch accounts, waive review or call author tests independent. No new tool denial was established; GitHub no-op ref access succeeded. This is unfinished implementation, not a universal support-ticket blocker.

EXACT NEXT ACTION: publish only this tested descendant after checking the live head. Inspect the newly retained pinned analyzer/models and correct compiler-predefine/implicit-dependency modeling against clean, benign diagnostic and missing-header owned controls. Require real native completion of all475 contexts without hiding diagnostics, reducing depth or blindly raising limits. Continue remaining runtime and normal worker/report integration, then independent review, gated merge/deployment and actual bilingual production acceptance. No SHIPPED declaration until every mandatory predicate passes.

## Immutable continuity

Parent ledger `533d8d5ea833ad4b897cff8be734c1ce831175fe:NICO-Ship-Checkpoint.md` and its3652/2195/a561/cbecc/fd1/254/b609/d236/a10/abb/1ebc chain preserve the complete contract, predecessor PR1627, prior native successes/failures, tools, worker/database evidence and approvals. Historical Bitcoin revision `0e9018e8b65611b0769545e177110e4b7fc51244` and run `comprun_7cc47a5a81695fa452354479ea23b422` remain unchanged. This is the only active mission ledger.
