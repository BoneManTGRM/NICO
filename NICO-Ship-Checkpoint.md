# NICO post-merge continuation — runtime scratch and failure retention

This is the sole active mission ledger. Preserve the complete predecessor at [31269344:NICO-Ship-Checkpoint.md](https://github.com/BoneManTGRM/NICO/blob/312693443b1e70c8a065de2c4e9ca329281d162a/NICO-Ship-Checkpoint.md), including its immutable 1bae/cefff/3ff747f8 chain and the original C0–C19 requirements. Nothing in this update reduces the frozen supported scope or approval boundaries.

## Recovered release and coordination

PR #1641 is merged at `0f14a8dba3c0fa6d11d982e007492a7f543ccfb7`. PR #1643 is also merged, at `312693443b1e70c8a065de2c4e9ca329281d162a`; its final source head was `bc36671c42b4bee73401d650d49f8b676f2f1ffd`. Do not reopen either PR or restore older versions. The corrective runtime work is based on actual main/tree `312693443b1e70c8a065de2c4e9ca329281d162a` / `0373f40d585471162c674dc7870fa6dee3784571`. Reconcile refs immediately before publication; use non-force updates and one writer.

The production frontend deployment `dpl_8peLtPtpFF839XWMbhwiQZkK2Dt1` is READY, carries that main SHA, and owns `app.nicoaudit.com`. Railway deployment `e045965c-ca52-42dc-858f-ef18bf563266` is SUCCESS with the same SHA. These are deployment/alias proofs, not complete serving/worker/assessment acceptance. No redundant deployment was requested. The service configuration's returned variable names did not include the configure-first qualification/activation settings. No setting was invented or enabled.

Frozen qualification target remains `bitcoin/bitcoin` at `bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`. The separate historical revision `0e9018e8b65611b0769545e177110e4b7fc51244` and run `comprun_7cc47a5a81695fa452354479ea23b422` remain untouched.

## Actual native failure recovered

Downloaded and verified run `36127119592` / job `108052224324` artifact `10862967834`, ZIP SHA256 `2a6056ce7b74ce1ec501c6b0777bf91f0a40a47ac8b5ae9df5da4fb606d0fe7b`. No oversized full-job log request was repeated. The native runtime artifact is `40af4a279f63e15944ae4afd2239a669bfbd7e6a20f09285bfc9b00f71000ec2`.

The frozen inventory contains 3,031 materialized files / 49,729,651 source bytes. The retained baseline passes 377 tests and 475 compiler contexts; generated inputs and cleanup are verified. All six selected functional tests pass, including wallet_ancient_migration and interface_ipc. The first failing native operation is `runtime-address-build`: exit 2 after 691,220 ms, with a killed linker followed by explicit `No space left on device`. Peak memory is 12,884,901,888 bytes; scratch capacity is 9,663,676,416 bytes. Reaching that ceiling and SIGKILL are not independent OOM-event proof.

The old producer continued into CTest after the failed build: 222/377 tests passed and 155 were skipped. UBSan and fuzz did not execute. The runtime remained incomplete. Exact retained-artifact replay reproduces `worker_runtime_evidence_invalid` because only the address sanitizer row exists, not the required address/undefined population. This is downstream rejection of incomplete execution, not permission to weaken the validator. Preserve all original failure bytes and statuses.

The descendant run `36129521112` on `977d657a02f7c449da9455b26896052f1261159c` was still running its native job `108068531516` at the last read; its contract/toolchain/source/owned-project jobs passed. It was neither cancelled nor duplicated. Its runtime producer blob is still the same uncorrected `801fa82afd4bc713c67a1cd9450e86c52118e846`; owner-liveness changes do not repair scratch exhaustion. Reuse its terminal evidence where applicable.

## Bounded corrective implementation

After retained functional results, reclaim only the completed baseline build and temporary functional-test directory. After each sanitizer's retained results, reclaim only that completed sanitizer build before starting the next phase. Fixed phase names, descriptor-relative symlink-resistant removal, top-level type/device checks, unchanged runtime UID and before/after filesystem measurements preserve the isolation boundary. Source, private analyst snapshots and unit-test data are not cleanup targets. The outer disposable-container cleanup remains unconditional.

Retain failed configure/build/discovery/corpus-stage operations before interpretation and do not execute their dependents. Evidence v2 binds the ordered reclamation operations, commands, users, exits, byte hashes, timing and space measurements. Legacy v1 remains readable with its original meaning and gains no reclamation claim. No required source/context/test, analyzer depth, resource/time ceiling, retry budget, approval control, credential scope or production setting changes.

Recorded RED: 21 failures. Identical GREEN: 21 passes. Thirteen additional negative/legacy cases were added after GREEN, not claimed as independently observed RED. All new tests now live in the already-required `tests/test_cpp_runtime_execution.py`; no additional workflow or duplicate qualification campaign is added. Final affected eight-file command: 168 passed, zero failures/errors/skips, terminal exit 0. Source and test Git blobs match locally tested bytes. A report-heavy broad command exceeded the local tool deadline and is not a complete suite pass. Local transport is substituted; real owned filesystem/symlink tests pass. Native Docker and full production proof remain unproven.

Exact verification and native locators: `docs/evidence/cpp-runtime-reclamation-20260925/verification.json`.

## PDF recovery and independent review still required

Run `comprun_29c30048215275ecbac35d179f71a1ed` remains the existing recovery target. PR #1643 records the 1,132-page composition-boundary failure, but its actual stored source/revision/contract and failing report inputs have not been retrieved in this continuation. Do not infer that it exercised the frozen complete C++ scope or that a 1,132-page PDF was stored. Recover through the supported authenticated operator workflow. Keep the 60-page boundary and verify English/es-MX continuation, unknown/missing/shared-page section boundaries, the canonical register and mandatory following content against actual inputs. Do not discard a report tail to make publication pass.

No authenticated operator session has been established here. Infrastructure access does not supply it; no password, admin secret or proof credential was extracted. No production assessment, database state, human disposition, approval or delivery authorization was created or changed. Direct external reads unavailable through a tool are not proof that the service is down.

The predecessor's independent-review allowance restriction remains binding. PR #1641's review-submission list is empty, but that does not disprove review elsewhere. Recover the complete review accumulator before claiming review completion. No exhausted unchanged review was resubmitted, no credits purchased, and no author self-review was represented as independent.

## Whole-row acceptance

| Predicate | State | Evidence / unmet scope |
| --- | --- | --- |
| C0 | UNPROVEN | Source/control/budgets and current release recovered; actual recovery-run contract/access and final qualification remain. |
| C1 | PASS | Retained complete frozen native inventory/acquisition; unchanged by correction. Normal-production exercise remains C18. |
| C2 | UNPROVEN | Prior native isolation passes; complete corrected combined workload still needs proof. |
| C3 | UNPROVEN | Dedicated final production worker/run/release binding absent. |
| C4 | UNPROVEN | Prior liveness repair preserved; final real-transport recovery/fencing acceptance remains. |
| C5 | UNPROVEN | Full current 475-context substantive static/fallback completion not proved. |
| C6 | PASS | Retained frozen baseline build/generated inputs and 475 compiler contexts; not production acceptance. |
| C7 | FAIL | ASan build failed; UBSan/fuzz absent. Corrected native instrumentation/replay proof required. |
| C8 | UNPROVEN | Final native/canonical/register/cross-format reconciliation remains. |
| C9 | UNPROVEN | Final static/runtime/report populations and exclusions remain. |
| C10 | UNPROVEN | Actual production score/assurance projection remains. |
| C11 | FAIL | Retained combined runtime exhausted scratch and reached memory ceiling; corrected workload unqualified. |
| C12 | UNPROVEN | Hosted owned predecessor passes; corrected owned and normal-production language controls remain. |
| C13 | FAIL | Required actual complete-scope Bitcoin report and failing-input PDF verification absent. |
| C14 | UNPROVEN | Actual bilingual/mobile/progress/refresh/recovery acceptance remains. |
| C15 | UNPROVEN | No human/history boundary changed; eligible exact-edition one-action proof remains. |
| C16 | UNPROVEN | Corrective hosted CI/security and complete independent review remain. |
| C17 | UNPROVEN | Main frontend/backend deployment mappings recovered; corrected release/worker/image serving chain incomplete. |
| C18 | FAIL | No qualified authorized normal-production frozen Bitcoin acceptance run established. |
| C19 | UNPROVEN | Final bilingual artifacts, repeated retrieval/hashes and complete closeout absent. |

## EXACT NEXT ACTION

Preserve the descendant native run and read its terminal retained evidence. Complete owned/focused verification of this correction, recover the actual report inputs and independent review, then use the normal narrow corrective PR process. Qualify only the changed candidate after the owned prerequisite. Complete full-project image/release binding and authenticated production control before the one justified frozen Bitcoin acceptance run. Keep all C0–C19 requirements and pending genuine human approval; do not declare SHIPPED at a code/test/merge/deployment milestone.
