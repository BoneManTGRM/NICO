# PR1641 continuation - publish reconciled compiler deadline and evidence repair

Continue existing PR #1641 on `feat/cpp-full-project-capacity`. This candidate is a non-force descendant of `3652a03965dfd7a96a45b5a6161daf8ec7b1042b`, tree `d4b2df3c1ea0204d178ebe9b3ebd5f2c3633a369`; observed main/base is `faaa10b037eb58e4175561b96dadf0d929764df4`. Record the containing publication SHA in PR #1641, not a self-hash commit. Recheck live refs before any subsequent mutation. The original NICO-CPP-Bitcoin-Execution-Prompt.md and C0-C19 contract remain binding. Publication is not full-assessment completion, merge readiness, deployment or report approval.

## Reconciliation and implemented behavior

The requested local repair was based on 2195a416, but the actual branch had advanced to 3652a039. Preserve that newer commit's versioned 600-second compiler allocation, boolean APIs, existing CLI switches, both native qualification commands and all 14 budget tests. Do not replace these with the older package's alternative string-version API. The compiler implementation and both qualification scripts remain byte-identical to 3652a039.

The additional changes now integrated are:

1. Enforce the unchanged 1,800-second parent deadline after native output/artifact retention and after compiler-proof validation/retention. Late bytes and successful earlier build/test evidence survive, but results at or after the deadline cannot qualify or start static analysis.
2. Preserve actual aggregate elapsed time when failure occurs before the separate static stage. Extended-budget probe receipts explicitly record schema v7 and budget version v2.
3. Bind live static preparation to the controller-selected compiler budget. Historical reconstruction still supports both published versions when no policy argument is supplied; explicit mismatches are rejected.
4. Port all 30 prepared regression cases onto the already-published boolean interfaces and add the suite to the existing workflow. Keep the newer 14-case suite and the existing exhaustive-static/deadline tests unchanged.

No context, generated file, required test, analyzer depth or diagnostic was removed. Compiler v1 remains 540 seconds; v2 remains 600 seconds; both retain 90 seconds/context and four workers. Parent baseline 1,800/1,810 seconds, separate static 600/610 seconds, aggregate 2,400/2,420 seconds, 50-minute hosted job, 4 CPU/12 GiB/no swap/256 PIDs/9 GiB scratch remain unchanged. No extra workflow dispatch, production activation, service, privilege or paid plan is introduced.

## Fresh local verification

The ported 30-case command first produced 10 expected assertion failures and 20 passes against 3652a039. The identical command after repair produced 30 passes, exit zero. This includes 1,799-second eligible output and 1,800/1,801-second rejection at native return, artifact retention and validation. No assertion was weakened to obtain a pass.

The complete updated workflow contract selection contains 32 files and 875 distinct cases. All 875 passed in nine disjoint batches: eight batches of 100 and one of 75; zero failures, errors or skips. Exact JUnit case membership equals the collected population, with neither omission nor duplication. The focused 30 and historical package's 861 are overlapping evidence, not additional test totals.

An outer container invocation containing batches 2 and 3 was interrupted after batch 2 completed. Batch 3 was subsequently run alone with identical cases and passed; the interrupted partial attempt is not credited. The initial RED command reported one existing SyntaxWarning. All modified Python ASTs, both embedded programs, all 13 workflow shell blocks and git diff --check pass. Workflow changes only register the new test file; existing permissions, job order, resource settings and pins are preserved.

Local dependency versions differ from the pinned hosted environment. These results are local contract verification, not full backend, native Bitcoin, hosted qualification or independent review. The reproducible selection, test results, source hashes, prior-package identity and limitations are recorded in [verification.json](docs/evidence/pr1641-3652-reconciliation-20260924/verification.json) and [test-results.log](docs/evidence/pr1641-3652-reconciliation-20260924/test-results.log).

## Hosted and retained native evidence

The source used here is artifact 10788757852 from run 35950988313: ZIP SHA-256 `8f5bdd812fae6b682261c0c7b21d62ab5a4fbdbbf99738c29c7d31a1465b3f05`. Its CI merge snapshot `11bf97a0bac8261cc11ae2dfaabda47e9484c2cf` maps to the observed parent tree, not a production merge. The archive and inner checksum were verified. Local Git metadata is only a detached source-export fixture without remotes and must never be pushed. Publish by building on the real upstream tree and parent.

At the direct connector read, parent 3652a039 NICO CI 35950988315 and Security Audit 35950988288 reported success, while Full Project Integration 35950988313 reported failure. Its Bitcoin artifact 10790085970 exists. Its native failure cause has not been inspected in this publication task; do not infer that cause from the older 540-second timeout. All checks must be reevaluated for the containing candidate.

Retain historical cbecc run 35934674741/job 107431082647/artifact 10783353302: 377 native tests passed, 475 compiler contexts checked. Retain a561 run 35945262906/job 107463662238/artifact 10787164500: 377 tests passed, 475 compiler contexts attempted but 474 completed before the 540-second cutoff; static analysis did not start. These different historical results are not interchangeable with new-policy qualification. Full original inventories, generated-byte hashes, owned controls, runtime measures and failure detail remain in the immutable parent checkpoint chain below.

## C0-C19 current whole-row status

| Predicate | State | Remaining proof or retained scope |
| --- | --- | --- |
| C0 | UNPROVEN | Full runtime contract and aggregate production qualification remain unfinished. |
| C1 | PASS | Historical complete frozen inventory/acquisition retained; production revalidation belongs to C18. |
| C2 | UNPROVEN | Prior isolated boundaries retained; complete workload/production enforcement pending. |
| C3 | UNPROVEN | Final full-workload receipt authority and identity qualification pending. |
| C4 | UNPROVEN | Normal-intake complete worker dispatch and ingestion remain unfinished. |
| C5 | UNPROVEN | Complete exhaustive Bitcoin static-analysis qualification outstanding. |
| C6 | UNPROVEN | Prior 475/475 success retained; current versioned policy requires native qualification. |
| C7 | UNPROVEN | 377 historical native tests passed; functional/integration/sanitizer/fuzz scope remains. |
| C8 | UNPROVEN | Complete native-to-canonical and report identity reconciliation pending. |
| C9 | UNPROVEN | Complete static/runtime populations and coverage reconciliation pending. |
| C10 | UNPROVEN | Final report scoring and assurance projections remain unverified. |
| C11 | UNPROVEN | Combined production workload/resource sufficiency remains unqualified. |
| C12 | UNPROVEN | 875 local contract cases pass; final native and supported-language qualification remains. |
| C13 | UNPROVEN | Actual full-supported Bitcoin Comprehensive report absent. |
| C14 | UNPROVEN | Final bilingual/mobile/progress/recovery proof pending. |
| C15 | UNPROVEN | Approval/history controls untouched; actual final-edition acceptance pending. |
| C16 | UNPROVEN | Final hosted checks and genuinely independent complete review pending. |
| C17 | UNPROVEN | PR unmerged; no new serving production release. |
| C18 | UNPROVEN | No normal production Bitcoin run exercising completed capability. |
| C19 | UNPROVEN | Final bilingual reports, hashes and repeated retrieval pending. |

No independent review occurred in this publication task. Prior review request 5802036311/reply 5802038248 reported exhausted allowance; do not retry unchanged requests, purchase credits, change accounts, waive the gate or describe author tests as independent review. No operator approval or client-delivery authorization was performed. Unrelated Railway changes remain untouched.

EXACT NEXT ACTION: inspect the containing commit's automatic contract/native qualification and the first actual failed native boundary, including parent artifact 10790085970 where useful. Preserve successful stage evidence and full required populations. Continue full runtime and normal worker/canonical/report integration; obtain independent review and final checks before gated merge/deployment. Verify actual frontend/backend/worker identities and run normal owned then authorized Bitcoin intake, including real English/es-MX report, exact-edition approval and repeated retrieval. Do not issue the full SHIPPED declaration before every mandatory predicate is proved.

## Immutable continuity

The complete prior ledger is [3652a039:NICO-Ship-Checkpoint.md](https://github.com/BoneManTGRM/NICO/blob/3652a03965dfd7a96a45b5a6161daf8ec7b1042b/NICO-Ship-Checkpoint.md). Its 2195/a561/cbecc/fd1/254/b609/d236/a10/abb/1ebc chain preserves the original C0-C19 meanings, PR1627 evidence, native successes/failures, worker/database/serving records and approval history. Historical Bitcoin revision `0e9018e8b65611b0769545e177110e4b7fc51244` / run `comprun_7cc47a5a81695fa452354479ea23b422` remains unchanged. This file is the sole active ledger; evidence files are verification records, not competing checkpoints.
