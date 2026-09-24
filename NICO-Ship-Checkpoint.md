# PR1641 continuation — preserve concurrent staging, enforce static depth and final deadline

Continue existing PR #1641 / `feat/cpp-full-project-capacity`. Parent `a561d77d7514aacead9cd1106932b860043f7316`, tree `7a0f77ba83707500509c30aa06bc267b3bfcb8f4`; last observed main/base `faaa10b037eb58e4175561b96dadf0d929764df4`. Recheck live refs before publication. Record the containing commit in the PR, not a self-hash commit. The original NICO-CPP-Bitcoin-Execution-Prompt.md and current C0-C19 meanings remain binding. This is not a completed production assessment.

## Concurrency and bounded correction

The branch advanced from cbecc7fb to a561d77d while an overlapping local patch was being verified. The ref check caught this before any branch update. Discard the older proposed tree, not the concurrent commit: preserve a561's separate no-network/noexec static sandbox, baseline destruction before analysis, generated-byte restoration, clean/positive/negative controls and current tests. Earlier uploaded Git blobs were unreferenced objects, not a published patch. The extracted selected-path local Git fixture is not upstream history and must never be pushed.

Two evidenced defects are corrected in the actual a561 descendant:

1. The new per-context pass used `--check-level=normal`, although the existing full-project pass requires `--check-level=exhaustive`. Restore the established depth for both owned and large controls; retain every original/generated/repeated context and all existing bounds. Native normal-level success is not proof of the changed exhaustive pass.
2. The separate 600-second stage checked its deadline before operations but could promote a final result returned, retained or validated at/after the deadline. A deterministic real-stage test reproduces false completion at 600 and 601 seconds for all three boundaries. Check the existing deadline after returned-byte retention and after validation/proof retention. Preserve late artifact bytes and cleanup, but keep the stage UNPROVEN. A 599-second result remains eligible. No timeout/resource increase or assertion weakening.

RED: seven failures and three passes. Identical repaired command: ten passes, exit0. Final affected eight-file command:196 passed in10.51s, exit0; one pre-existing SyntaxWarning in express_score_assurance_export_v1.py. This is local contract verification, not native execution or independent review. Log SHA-256 `3fc52b0c04e407339970ac670cdd135950e13d6b5aeca3a8ce8af895ed3a62f8`; JUnit `786bcb911709c51e8fe05a74e698303a950cb7fc030561f95785dece0e8391bc`. Counts overlap; do not add historical803 or predecessor274 counts. Changed Python AST, standalone collector compilation and git diff --check pass. No unchanged oversized local command was rerun.

## Retained native owned proof for a561, scoped to normal check level

Run35945262906 has successful contract, LLVM, exact-source and owned integration jobs. Owned job107462257912's artifact10786249375 is1,643,741 bytes; ZIP SHA-256 `c7ced4177287ee56a629fc43f0ff8ff8b23af110039035a633627d3a9fd4f997`. Owned snapshot-control receipt SHA-256 `db714081a240c7390baf87c30104ee5926db0fb3763fa2ce4cb95689f805fef8`.

Reconstructed its original request with the immutable parent analyzer code, revalidated snapshot/compiler/static native bytes and all retained hashes, and compared canonical projections. Clean:4/4 contexts, zero findings,835ms static stage,22,720,512-byte peak. Positive:4/4 contexts, the two real `uninitvar` and `unassignedVariable` candidates on the deliberately uninitialized generated function,854ms,22,355,968-byte peak. Both actual noexec/network boundaries and cleanup pass; unused generated header stays compiler-unvisited. Negative rejects the header link before static execution and cleans up. Do not impose an invented one-finding expectation: the pinned tool legitimately emits two candidates. None is human-reviewed or production-qualified.

Clean native static hash `67859b67b32bb98ef057ce95bd4b4d0e45e8954697968c2fc572d06d76afa131`; positive `dcaf41ac4a37d5e74735b85cd09186c912f62fc6fb163f7533e582de12bf1879`. These prove the parent normal-level control, not the new exhaustive-level execution.

The same run's Bitcoin job107463662238 was still in progress at the last direct observation. Preserve it; do not cancel or manually duplicate it. Inspect its eventual native outcome and retain the first failing layer. The next candidate's required automatic CI may run normally.

## Retained Bitcoin baseline/compiler proof and frozen scope

Unchanged accepted run35934674741/job107431082647, artifact10783353302:12,125,974 bytes; ZIP SHA-256 `c1657823d745a9a07e2ad83d3502f9c3b9e7405b3f9768a4f20d7cb11f035f48`. Frozen Bitcoin `bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`:3,248 inventory entries,3,031 blobs,49,729,651 source bytes;475 required=attempted=checked compiler contexts,445 original and29 generated distinct files, one original twice.377 discovered=executed=passed native tests, zero skipped.121 generated files/32,033,843 raw bytes;406 original and92 generated compiler-visited headers. These are not analyzer header coverage.

Database `fc89aa69b2a369417cbff01d2784225bd23547827b1f7fd946669f919526aa1b`. Linux Debug wallet/tests/IPC/embedded data remain ON; GUI/benchmarks/ZeroMQ/other platforms remain outside the frozen baseline. Duration1,598,401ms; peak9,023,561,728 bytes; boundary and cleanup verified. Image config `sha256:59b69a2a01ed0308556400270a492b216dcb92efe6b4d78442567ac9e113fc62`.

Preserve the parent's separate bounded stages: baseline1,800s/wall1,810s; static600s/wall610s,540s analyzer/90s per context/four workers; aggregate2,400s/wall2,420s. Each uses4CPU/12GiB/no-swap/256PID/9GiB scratch. No new spend/privilege/service/resource setting is introduced by this repair. Exhaustive workload sufficiency remains unproven; never suppress diagnostics, drop contexts or reduce depth to pass. Changed static depth/deadline invalidates dependent static qualification, not historical baseline bytes or tests.

## Current checks, review and production gaps

PR NICO CI run35945262901/backend job107461697467 failed `test_watchdog_automatically_recovers_hung_renderer_without_second_advance` at `second_started.wait(1.5)`:11,598 passed,1 failed,136 skipped. The unchanged watchdog file's focused local command passed all4 tests in1.38s. The hosted root cause is unresolved; a local pass does not waive the required check. No watchdog production code or timeout assertion was changed. Parent security result was success; new candidate checks remain required.

Actual PR reviews and requested reviewers were empty. Prior Codex request5802036311/reply5802038248 exhausted review allowance; no independent review occurred. Do not repeat unchanged requests, buy credits, change accounts or call author review independent. Establish any alternative already-authorized mechanism before using it. The earlier recorded Bitcoin discovery denial remains separate from permitted generic implementation; establish its real scope and supported resolution without routing around a rejected action.

Normal production dispatch still uses the existing worker/lease/receipt path; project-wide preparation/static receipts are not yet connected as a complete production assessment. Required Bitcoin integration/sanitizer/fuzz work remains unfinished. Production activation, merge, deployment, English/es-MX actual Bitcoin report, exact-edition approval and repeated retrieval are not proved. Vercel/Railway projects were recovered, not newly deployed; no serving release proof or production data/credential/approval mutation is claimed.

## C0-C19 whole-row status

| Predicate | Status | Exact remaining proof or retained subproof |
| --- | --- | --- |
| C0 | UNPROVEN | Runtime target groups, full aggregate production budgets and restriction scope remain unresolved. |
| C1 | PASS | Complete frozen qualification inventory/acquisition in artifact10783353302; production revalidation belongs to C18. |
| C2 | UNPROVEN | Baseline and parent owned noexec isolation pass; changed complete workload/production enforcement remains. |
| C3 | UNPROVEN | Existing identity proofs retained; new full execution receipt binding not qualified. |
| C4 | FAIL | New project-wide evidence is not yet wired through normal durable production completion. |
| C5 | UNPROVEN | Parent owned normal-level native pass; new exhaustive475-context completion pending. |
| C6 | PASS | Frozen baseline build/generated bytes/475 compiler contexts/header evidence verified. |
| C7 | UNPROVEN |377 native tests pass; required Bitcoin integration/sanitizer/fuzz scope unfinished. |
| C8 | UNPROVEN | Parent static candidates retain identities; actual canonical/report cross-format integration remains. |
| C9 | UNPROVEN | Baseline/compiler populations verified; new static/runtime/canonical reconciliation remains. |
| C10 | UNPROVEN | Prior truth/scoring protections retained; actual new report inputs and projections not verified. |
| C11 | UNPROVEN | Baseline measured; complete exhaustive/static/runtime workload not qualified. |
| C12 | UNPROVEN | Parent owned controls and196 affected local tests pass; changed native and full regressions remain. |
| C13 | UNPROVEN | Actual complete-scope Bitcoin structured report and rendered PDF absent. |
| C14 | UNPROVEN | Affected production bilingual/mobile/progress/recovery acceptance not executed. |
| C15 | UNPROVEN | Human/history controls untouched; actual eligible one-action and edition checks remain. |
| C16 | FAIL | Required hosted watchdog check and independent complete review unresolved; new checks pending. |
| C17 | FAIL | PR unmerged; no new merged release/serving mappings. |
| C18 | FAIL | No normal production Bitcoin run exercising the completed capability. |
| C19 | UNPROVEN | Qualification hashes retained; final bilingual artifacts/retrieval/closeout not established. |

EXACT NEXT ACTION: publish only this reconciled four-file descendant after a fresh head check; inspect preserved parent Bitcoin output and the new automatic owned/exhaustive qualification. Repair the first native failure without changing required populations. Continue generic durable-worker/canonical/report integration, concrete runtime scope and independent-review resolution while hosted execution runs. Merge/deploy only after pre-merge gates, verify each platform, run normal owned then authorized Bitcoin intake, and inspect the real bilingual report/approval/retrieval evidence. No full SHIPPED claim until every mandatory row passes.

## Immutable continuity

Full parent ledger is `a561d77d7514aacead9cd1106932b860043f7316:NICO-Ship-Checkpoint.md`; its cbecc/fd1e93/2543801b/b609/d236/a10/abb/1ebc chain preserves original C0-C19, PR1627, exact controls/tools, successful and failed native receipts, worker/database/release evidence and approval history. Historical Bitcoin revision0e9018e8b65611b0769545e177110e4b7fc51244/runcomprun_7cc47a5a81695fa452354479ea23b422 remains unchanged. This is the sole active ledger.
