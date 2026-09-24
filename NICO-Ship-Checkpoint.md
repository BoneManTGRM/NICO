# PR1641 continuation — preserve native Boost version metadata

Continue PR #1641 / `feat/cpp-full-project-capacity`. This repair is based on parent `516d6d83eb5d73f85374769dd3d9af26a6bcbc37`, tree `3783958df114ec510ed3c0398f8283be09aa6f42`; last directly observed main/base `faaa10b037eb58e4175561b96dadf0d929764df4`. Recheck live refs and preserve concurrent descendants before publishing. Record the containing commit in the PR, not a self-hash commit. The original NICO-CPP-Bitcoin-Execution-Prompt.md and all stronger C0-C19 requirements remain binding. Publication is not merge readiness, deployment or a production report.

## First actual failure and repair

Current-parent integration run 36035386439 / owned job 107766534356 failed its generated-context control. Bitcoin job 107768065382 was skipped, not executed or passed. Owned artifact 10825472844 is 4,370,710 bytes, SHA256 `f0a0a655ada3802df178d50fe35ad343ddb482e4dd5ce9fbf6c940053280fd4f`. Source artifact 10826575168 is 4,477,387 bytes, SHA256 `9ad984d31fe5cbaee13170b05ed5103e03be8271e86436e0fb3f4f3cab4106bf`; its inner archive checksum and exact parent tree were verified.

The new Boost API modeling classified `boost/version.hpp` as a modeled API header and stopped projecting its bytes. The pinned library model does not provide the installed `BOOST_VERSION` macro, which the unchanged owned control requires. Replay of exact retained clean inputs using the pinned Cppcheck 2.17.1 reproduces two failed and two completed contexts with preprocessing errors. This is a producer defect, not a flaky CI check.

`header_model` now keeps this compiler-resolved version metadata header as native input, with the existing exact bytes, digest, private projection and missing/corrupt-input rejection. Other compiler-resolved system Boost API headers retain the existing pinned model. No Boost version is fabricated, no repository name is special-cased, and no first-party source or required population changes. The explicit derived model policy is `gcc14-unix64-public-c-cpp20-posix-boost-native-version-v3`. Dependent analyzer/model evidence must be requalified; unchanged source/build/compiler evidence is retained historically.

## Verification actually completed

Three prepared behavioral tests reproduced the absent projection before the repair. The current affected environment/static/stage/preprocessing/configuration selection passes 157 distinct tests with zero failures/errors/skips, exit 0. Python syntax and both embedded programs compile. Full workflow collection contains 941 cases in 35 files, but a complete local full-suite pass is NOT claimed: report-heavy batches exceeded the 26-second local command allocation; batch 3 was split into the same core and four individual report cases and passed. These counts overlap the 157 and are not additive.

Actual local native replays, using hash-verified retained original/generated/ compiler/environment bytes and the exact pinned analyzer, now yield clean 4/4 completed with zero candidates, diagnostic 4/4 with the two intentional candidates, and failure when the required version header is deliberately removed. Native version-header SHA256 is `90e046b8e3138a61c692abdd9bc2e45c1a95996cc5a8031cce1f110de5e64a70`. Execution uses UID1001 and local CPU/memory/output limits; it is NOT Docker/hosted-image/Bitcoin/production proof. The initial negative replay harness assumed success; it was corrected to assert the actual failure envelope for the negative case without altering product output. Exact source hashes, native request/output hashes and verification limitations are in `docs/evidence/pr1641-boost-version-20260924/verification.json`; RED/GREEN terminal results are in `test-results.log`.

## Preserved scope, identity and controls

Frozen Bitcoin stays `bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`. Preserve all 475 required configurations, Linux Debug wallet/tests/IPC/embedded data, generated/header evidence, 377 native tests and declared runtime scope. All existing time/CPU/memory/process/scratch/request/transport/storage limits, exhaustive analyzer depth, raw artifacts, tenant/run/revision/release binding, approval and historical report rules remain unchanged. No duplicate workflow, new resource class, spending, privilege or production activation is introduced.

Retain the preceding XML compaction (50e501e1), hash-bound qualification summary (e3722f47), compiler-resolved Boost model (516d6d83), and earlier executable-source recovery. The separate first-party `src/coins.cpp` Cppcheck internal error from retained 50e501e1 evidence remains unresolved and cannot earn completion credit. The latest model has not yet reached a valid Bitcoin qualification because the small-control gate failed. Full normal intake-to-worker-to-report integration, runtime scope and independent review remain unfinished; permission is not the missing requirement.

## Whole-row C0-C19 status

| Predicate | Status | Current scope / remaining proof |
| --- | --- | --- |
| C0 | UNPROVEN | Anchors/authority recovered; complete runtime scope and aggregate production qualification remain. |
| C1 | PASS | Complete immutable frozen inventory retained; production revalidation belongs to C18. |
| C2 | UNPROVEN | Historical isolated boundaries retained; full workload/production enforcement remains. |
| C3 | UNPROVEN | Complete production identity and receipt authority binding remain. |
| C4 | FAIL | Full configure-first evidence is not connected through normal durable production completion. |
| C5 | FAIL | Latest Bitcoin job skipped; prior analyzer internal error remains unqualified. |
| C6 | PASS | Historical baseline/generated/compiler/header proof retained, not new production proof. |
| C7 | UNPROVEN |377 baseline tests historically passed; declared integration/sanitizer/fuzz scope remains. |
| C8 | UNPROVEN | Actual canonical/report identity reconciliation remains. |
| C9 | UNPROVEN | Required populations preserved; complete analyzer/runtime/report reconciliation remains. |
| C10 | UNPROVEN | Scoring unchanged; final actual report projections remain. |
| C11 | UNPROVEN | Correct complete combined workload capacity remains unqualified. |
| C12 | FAIL | Current hosted owned control failed; local repaired native controls pass but hosted qualification is required. |
| C13 | UNPROVEN | Actual complete-scope production Bitcoin report absent. |
| C14 | UNPROVEN | Final bilingual/mobile/progress/recovery acceptance absent. |
| C15 | UNPROVEN | Approval/history untouched; final eligible exact-edition acceptance remains. |
| C16 | FAIL | Complete native qualification and independent final-candidate review remain. |
| C17 | FAIL | PR unmerged; no new serving production release. |
| C18 | FAIL | No normal production Bitcoin run exercising complete capability. |
| C19 | UNPROVEN | Final bilingual artifacts, hashes and repeated retrieval absent. |

Prior Codex review request5802036311/reply5802038248 exhausted allowance. Do not retry unchanged requests, buy credits, switch accounts, waive review or call author tests independent. The earlier rejected Bitcoin build/config/test/sanitizer/fuzz discovery must not be evaded; it is separate from this permitted generic adapter correction. No new universal tool denial is claimed. GitHub non-force publication is available. No merge, deployment, operator approval or client-delivery authorization occurred.

EXACT NEXT ACTION: publish the verified Boost metadata repair as a non-force descendant, then inspect automatic owned clean/diagnostic/missing-input qualification and the frozen Bitcoin execution. Resolve the first actual remaining analyzer failure without dropping contexts or lowering depth. Continue permitted full runtime and durable normal-intake/canonical/report implementation while hosted qualification runs. Obtain genuinely independent review and final gates before merge/deploy, then prove exact frontend/backend/worker serving identities and actual authorized English/es-MX production Bitcoin reports and protected retrieval. No SHIPPED claim before every mandatory row passes.

## Immutable continuity

The complete preceding ledger is `516d6d83eb5d73f85374769dd3d9af26a6bcbc37:NICO-Ship-Checkpoint.md`. Its e3722f47/50e501e1/8f7f1248/e118/95f/533d/3652/2195/a561/cbecc chain retains all prior native success/failure, original C0-C19 crosswalk, merged PR1627, runtime and human-approval history. Historical Bitcoin revision `0e9018e8b65611b0769545e177110e4b7fc51244` / run `comprun_7cc47a5a81695fa452354479ea23b422` remains unchanged. This is the sole active mission ledger.
