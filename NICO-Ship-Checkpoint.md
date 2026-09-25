# NICO post-merge continuation — register conservation and native resource failure

This is the sole active mission ledger. Continue the original full C/C++ and frozen Bitcoin production-report contract; no C0–C19 requirement is waived. This checkpoint replaces obsolete pre-merge status, not the retained evidence.

## Immutable continuity and current writer

Complete predecessor: [31269344:NICO-Ship-Checkpoint.md](https://github.com/BoneManTGRM/NICO/blob/312693443b1e70c8a065de2c4e9ca329281d162a/NICO-Ship-Checkpoint.md), blob `75a804d77f1cb5d9e659bf18a1fa1f122edffd77`. Its immutable predecessor [1bae247a](https://github.com/BoneManTGRM/NICO/blob/1bae247a9729512a809e3ec20930ae067680f7db/NICO-Ship-Checkpoint.md) preserves the earlier contract, independent-review findings and native evidence chain.

Main was re-read as `312693443b1e70c8a065de2c4e9ca329281d162a`, tree `0373f40d585471162c674dc7870fa6dee3784571`. PR #1641 is merged at `0f14a8dba3c0fa6d11d982e007492a7f543ccfb7`; PR #1643 is merged at current main. Do not reopen or recreate either PR.

One narrow corrective branch: `fix/client-pdf-register-conservation`, created from exact current main after the open-PR query returned no corrective PR. Test commit `10176d8bc11d8370f30229c57a3592761e8045a4`; application/test candidate `798c49a8813a989b676c2699833526d5141f3f87`; evidence index committed at `fef6a20532934530ea77fd431b9c3e6c815bba30`. Subsequent documentation does not change those tested source bytes. Re-read this branch's actual head and any open PR before writing. No force push, competing writer or local fixture Git history was used.

GitHub create-branch/create-file/update-file operations actually succeeded. A blanket claim that this session cannot publish source is obsolete. Platform names alone still do not prove other permissions.

## Frozen target and history

Qualification target: `bitcoin/bitcoin` at `bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`. Preserve all 475 compilation contexts, generated inputs and repeated configurations, all 377 baseline tests, Linux Debug wallet/tests/IPC, required static completion, declared functional/sanitizer/fuzz scope and original exclusions.

The distinct historical revision `0e9018e8b65611b0769545e177110e4b7fc51244` and run `comprun_7cc47a5a81695fa452354479ea23b422` remain unchanged. Neither is a substitute for the frozen qualification target.

## PDF correction actually published

The merged composer skipped all pages after a legacy-register heading until a recognized resume heading. Owned bilingual regressions reproduced loss of unknown following primary sections, shared-page primary content, and prefix/prose boundary confusion. Candidate v3.7 requires exact register-heading lines, preserves recognized mixed primary pages, removes recognized finding/field continuations, and exits discard on unclassified content. Ambiguous retained content still faces the unchanged 60-page fail-closed gate. Canonical register, native evidence, scores and human gates are unchanged.

Verified remote/local blobs: composer `8cd348edce7cbc549f699d30164e2f8d0e7bea4b`; new tests `8b28f284c371ec58573e8a8c0aa5284bd5cf46eb`. Existing composer tests remain byte-identical at `4805e60c80c96a2174ed70253976e8860c08ed5a`.

Recorded RED: 16 failed / 6 passed on exact main composer. Identical GREEN: 22 passed. Two disjoint affected suites: 37 + 14 = 51 distinct passes, zero failures/errors/skips. The 22 are already included in 37. Local Python 3.13 / pypdf 5.9.0 is not the pinned hosted environment; full CI and golden parity are not claimed. One unrelated pre-existing invalid-escape warning is retained.

Two labeled synthetic five-page EN/es-MX outputs were rendered and visually inspected. Cover and two retained primary pages were pixel-identical to their base pages; no off-page text spans were found. This is boundary-fixture evidence only, not actual Bitcoin output, full language parity or physical-iPhone acceptance. Full hashes, commands, local JUnit identities and native artifact references are in [verification.json](docs/evidence/pr1643-register-conservation-20260925/verification.json).

Actual failing report inputs for `comprun_29c30048215275ecbac35d179f71a1ed` have NOT been obtained. The original 1,132-page exception does not prove a PDF was stored. The correction is not qualified against those inputs and must remain unmerged until applicable verification/review gates pass.

## Native failure resolved to its actual first boundary — not repaired yet

Both completed qualification runs failed in the combined native step, with evidence upload successful:

- [36127119592](https://github.com/BoneManTGRM/NICO/actions/runs/36127119592), job `108052224324`, source `1bae247a9729512a809e3ec20930ae067680f7db`; retained baseline artifact `10862967834`, ZIP SHA256 `2a6056ce7b74ce1ec501c6b0777bf91f0a40a47ac8b5ae9df5da4fb606d0fe7b`.
- [36129521112](https://github.com/BoneManTGRM/NICO/actions/runs/36129521112), job `108068531516`, final PR1641 source `977d657a02f7c449da9455b26896052f1261159c`; retained baseline artifact `10865403350`, ZIP SHA256 `4249b1b26d0cabc76704e0f29b093c708acdc0736b87d4f0ba09a7ffa0f361df`.

Downloaded ZIPs and exact runtime artifacts were hash-verified. Both show 377/377 baseline tests passed, 475/475 compiler contexts checked, and all six frozen functional tests passed: feature_shutdown.py, mempool_datacarrier.py, p2p_seednode.py, rpc_openrpc.py, wallet_ancient_migration.py, interface_ipc.py.

The AddressSanitizer build then exits 2, without timeout or output truncation. Its first linker failure says `ld terminated with signal 9 [Killed]`; subsequent compiler/assembler output says `No space left on device`. The ASan CTest invocation exits 8 with 222 executed/passed and 155 skipped out of 377 required. UBSan, bounded fuzz and the subsequent fresh static stage did not execute. Native runtime error is `worker_runtime_sanitizer_failed`, complete=false. No skipped required test is counted as completed.

Both probes reached a recorded 12,884,901,888-byte memory peak, with a 9,663,676,416-byte scratch capacity; isolation boundary and cleanup flags were true. The original and descendant ASan builds took 691,220ms and 509,792ms respectively. No memory.events OOM-kill counter or per-directory peak allocation was retained: memory pressure is supported, but signal 9 alone does not prove which process killed the linker. No resource ceiling was changed.

Data-only replay with the exact current runtime-validator blob `801fa82afd4bc713c67a1cd9450e86c52118e846` reproduces `worker_runtime_evidence_invalid` at line 430. The actual retained plan hashes to `09588b0e6222ec84538b9467c0c8366debbfee06accf22f54078a54c961976d1`, matching both receipt and evidence. The first rejected invariant is required sanitizer kinds `[address, undefined]` versus retained `[address]`. The validation error is downstream of the native failure; suppressing it cannot repair the missing workload.

No native implementation changed, no qualification was cancelled, and no new native campaign was started. Two materially similar failures make another unchanged retry unjustified. A phase-workspace/resource correction needs an owned reproducer and measured native proof before another large run. Preserve baseline, compiler and functional subproofs; invalidate only affected later execution evidence after a real correction.

## Current release and protected report-access boundary

Vercel resolved the live `app.nicoaudit.com` alias to production deployment `dpl_8peLtPtpFF839XWMbhwiQZkK2Dt1`, READY, source `312693443b1e70c8a065de2c4e9ca329281d162a`. Railway read-only platform inspection confirmed deployment `e045965c-ca52-42dc-858f-ef18bf563266`, same source, successful healthcheck on 2026-09-25 at 12:23:05 UTC. These establish frontend/backend deployment mappings, not a qualified worker image or complete end-to-end execution.

The existing protected Assessment Worker workflow already has a 155-minute outer job bound. Do not reintroduce or repair the obsolete 45-minute value. Existing 9,000-second runtime-capable durable contract, renewable 300-second lease, one-attempt rule and inner resource limits remain intact; combined sufficiency is still unqualified.

Railway's available read-only operations expose deployment/configuration and bounded logs, not NICO run records, canonical report inputs, diagnostic PDFs or artifact metadata. No database credentials were retrieved, no database read was performed, and persistence/state of `comprun_29c...` remains UNPROVEN. HTTP 200 /continue traffic was observed for a different run `comprun_702dd65cbc9013a81c1819ef68044f8b`; this proves traffic only, not its source, progress, report generation or completion. Do not transfer a historical 83% note to either run.

A read-only Firecrawl browser attempt requested zero-data-retention handling and was rejected because that feature is not enabled for its team. No authenticated operator session or protected input was obtained. This is a scoped access/provider-capability boundary, not a universal ban on GitHub engineering or an excuse to weaken authentication. Do not request secrets in chat or assume that an ordinary phone sign-in transfers a session to this tool.

## Review accumulator

PDF-CONSERVATION-1: locally repaired; 22 new tests, 51 affected passes, synthetic render proof. Actual production-input verification remains open.

NATIVE-CAPACITY-1: OPEN. Reproduced in two retained native artifacts. No source correction, new resource measurement or successful combined runtime qualification yet.

ACTUAL-PDF-REPLAY-1: OPEN / access boundary. Need the exact failing run's supported authenticated diagnostic/read operation or a legitimate existing operator session. Do not invent a diagnostic export button, run state or artifact.

PDF-SCOPED-REVIEW-1: an independent read-only Railway agent inspected the exact base/candidate composer. It initially recommended keeping discard state through unknown content. That proposal was replayed in an isolated process against the unchanged 22 tests: 2 failed / 20 passed, losing the mandatory following Location page in both locales. Candidate source was not altered. The reviewer withdrew that proposal and retained NOT READY FOR MERGE because actual failing-input verification is missing. Its response also contained inconsistent prose/counts; only verified findings and the missing-input disposition are accepted. This is limited source review, not independent test execution, complete-capability review or production approval.

INDEPENDENT-REVIEW-1: OPEN for the complete capability and final corrections. Preserve prior allowance exhaustion and unresolved historic findings. Do not substitute author tests, the limited external review, CI, or skill loading for complete independent review; no new credits or quota workaround were used.

## C0–C19 whole-row acceptance

Statuses below concern the full current mission, not whether one historical subproof exists. Valid retained baseline proofs are preserved; renderer-only edits do not invalidate native content evidence.

| Predicate | Status | Evidence and remaining scope |
| --- | --- | --- |
| C0 | UNPROVEN | Refs, authority, target and bounded contract recovered; actual operator/run access and complete qualification remain unresolved. |
| C1 | UNPROVEN | Prior frozen complete-inventory/acquisition proof retained; final production inventory and immutable run contract not read. |
| C2 | UNPROVEN | Native boundary/cleanup evidence retained; whole supported combined workload not completed. |
| C3 | UNPROVEN | No final production worker/tenant/run/source/configuration/release receipt chain. |
| C4 | UNPROVEN | Owner-liveness repairs and prior controls retained; full real production long-job recovery/fencing path unverified. |
| C5 | UNPROVEN | Static proof from prior attempts retained where applicable; the two current combined failures never reached static completion. |
| C6 | UNPROVEN | 377-test baseline and all475 compiler contexts retained; final production generated/header/build reconstruction still unverified. |
| C7 | FAIL | ASan build fails;155 required ASan tests skipped; UBSan/fuzz not executed in either retained combined attempt. |
| C8 | UNPROVEN | Actual final native/canonical/register/export reconciliation not obtained. |
| C9 | UNPROVEN | Known native populations retained; complete production memberships/exclusions/output hashes not verified. |
| C10 | UNPROVEN | No final actual-run score/assurance projection verified; scoring code unchanged. |
| C11 | FAIL | Combined native workload exhausts scratch and reaches the memory ceiling; no qualified resource/lifecycle correction. |
| C12 | UNPROVEN | Historical hosted owned controls retained; generic normal-production C/C++ and affected supported-language controls remain. |
| C13 | UNPROVEN | Actual Bitcoin structured output and rendered review PDFs not obtained; synthetic PDF proof is not this row. |
| C14 | UNPROVEN | Bilingual synthetic boundary tests pass; actual locale/mobile/progress/refresh and physical-iPhone proof absent. |
| C15 | UNPROVEN | No authentication/approval/history changes made; final exact-edition human workflow not verified. |
| C16 | UNPROVEN | Limited source review obtained; actual-input verification, exact hosted checks/security and complete independent review remain. |
| C17 | UNPROVEN | Main frontend/backend deployment mapping verified; final qualified worker/image/receipt binding absent. |
| C18 | UNPROVEN | No authenticated frozen-target normal-production run has been verified through the required full supported scope. |
| C19 | UNPROVEN | Native and local evidence indexed; actual bilingual report hashes/repeated retrieval/closeout still absent. |

## EXACT NEXT ACTION

Keep the PDF correction as one draft corrective PR on its existing branch. Obtain the actual failed report inputs through a supported authenticated operation before claiming the 1,132-page failure repaired; replay them against exact base/candidate and inspect all rendered mandatory sections. Observe normal hosted CI without duplicating native qualification. Resolve any independently reproduced review finding before merge.

For the independent native repair, use an owned phase-workspace reproducer to measure baseline/functional/ASan allocation and test reclamation or isolation ordering under the unchanged resource contract; preserve captured/generated/compiler evidence, source immutability and cleanup protections. Do not blindly increase limits or disable tests. Qualify a materially corrected candidate only after its owned controls pass, then finish full review/image release and real normal-production control/Bitcoin acceptance. The report-access boundary does not make this remaining engineering complete.

No new production assessment, receipt import, qualification flag, image publication, deployment, merge, specialist/operator approval or client-delivery authorization was performed in this continuation. No actual Bitcoin EN/es-MX artifact link or hash has been verified. Never declare SHIPPED from this checkpoint.
