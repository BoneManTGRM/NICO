# Active mission: Comprehensive C/C++ and Bitcoin qualification

Updated 2026-09-23. Continue PR #1641 on `feat/cpp-full-project-capacity`. The owner's `NICO-CPP-Bitcoin-Execution-Prompt.md` and C0-C19 contract remain governing. No replacement branch, permission bypass, automatic human approval, or full-capability completion claim.

## Current increment and immutable continuity

The publication parent is `934bcf6bf30e5b011adabc7764cf75dcecdf92b9`, tree `ae2f8dbba7f1400742be553f27f092951565b02c`; observed main/base is `faaa10b037eb58e4175561b96dadf0d929764df4`. Resolve this enclosing commit and current PR head from GitHub instead of making a self-referential documentation commit.

The complete preceding checkpoint is preserved at [934bcf6b](https://github.com/BoneManTGRM/NICO/blob/934bcf6bf30e5b011adabc7764cf75dcecdf92b9/NICO-Ship-Checkpoint.md): Git blob `8a9109d1bb4fcee53be16669c614594e2e7712ad`, SHA-256 `9077d41e08b48d610a6ece39746e9887dd03147b6ba31a250bb4a833c8717210`, 12,768 bytes. It retains the exact older 589,918-byte checkpoint, PR #1627 worker/registry/database evidence, original authorization/restrictions, historical reports and all prior failure outcomes. This is the only active ledger; immutable historical next-action prose is not a current instruction to restart.

Qualification target remains `bitcoin/bitcoin@bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`. Historical report target `0e9018e8b65611b0769545e177110e4b7fc51244`, run `comprun_7cc47a5a81695fa452354479ea23b422`, remains separate. Production entrypoint is `https://app.nicoaudit.com`; no deployment or live Bitcoin run is claimed here.

## NESTED-CMAKE-1: supported subdirectory configuration

First divergence: existing compilation-database validators reject a legitimate CMake `add_subdirectory` working directory, even when source, includes, compiler and the complete required unit population remain bound. Owned reproduction: ten expected failures and fourteen unchanged rejection controls.

Smallest correction extends the existing parser, execution and canonical reconstruction. Opt-in configuration v6 wraps validated v4/v5 with `cmake_layout=nested-source-v1`. Canonical child directories beneath the matching build root are accepted; cross-configuration, sibling, traversal, malformed and relative directories are rejected. Source/include operands remain absolute and restricted. Actual recompilation still uses the private analyst directory, never the untrusted database working directory.

Old v1-v5 meanings are unchanged. The existing compiler program remains byte-identical, SHA-256 `e733ce201f07381a5a5de7585b6296c3b9d21a5ca236246fc0b10dbd1140ae71`; the separately selected nested program is `388a56484e82b3e36f8776b8c14de2e1971b0200b03fe689154744dbb3a15e4d`. Snapshot program is unchanged, `69260ed6a9832caa309c34c70607ca7c8b0136c70abf1395285a42ac1537d084`. Both original native parent receipts reconstruct exactly with the new source; old evidence is not upgraded into v6 proof.

## PROJECT-DEPS-1: pinned inputs and meaningful owned control

The existing tool provisioner now supports one fixed reviewed dependency lock: Boost 1.74.0 development headers and matching SQLite 3.40.1 runtime/development packages. Official Debian bookworm amd64 metadata supplies exact package versions, lengths and SHA-256 values in `docker/assessment-project-dependencies.lock.json`. Total compressed inputs are 11,371,836 bytes. This is not a complete Bitcoin dependency inventory, installed-runtime proof, or a vulnerability-free claim.

Downloads remain credential-free, HTTPS-only, nonredirecting and byte/hash checked, with a 30-second aggregate dependency budget and 16 MiB aggregate input ceiling. Partial evidence is preserved on failure. No public package-install endpoint or arbitrary dependency selector is introduced. The existing disposable tool-image recipe verifies the input manifest and uses extraction only, without package install hooks or build networking. Input receipt and hashes are retained inside the image. Assessed source remains outside tool-image construction.

The existing native positive and intentional-negative controls now explicitly request a nested library that uses Boost headers and calls SQLite at runtime. Header-version assertions, actual linking/runtime-version checks, source/generated/image-header evidence, original failed-test semantics, both sanitizer binary replays and bounded fuzz remain required. The default fixture is unchanged. New tests and package receipt retention are added to the existing workflow, not a parallel proof pipeline.

Every existing assertion, contents-read-only workflow permission, five-minute job bound, 2 CPU/2 GiB/256 PID class, smaller profile, one-attempt lease contract and report approval boundary remains. This increment does not publish an image registry artifact or activate a production profile.

## Verification actually observed

- Nested-directory RED: 10 failures / 14 existing rejection controls passed.
- Dependency provisioner RED: 3 failures / 17 controls passed; actual dependency-fixture API RED: 2 failures; malformed dependency-name RED: 2 failures / 3 controls passed.
- Fresh final publication command: `python -m pytest -q tests/test_cpp_nested_cmake.py tests/test_cpp_project_dependencies.py tests/test_cpp_fixture_tree.py tests/test_cpp_fuzz_tool_provisioning.py tests/test_cpp_integration_workflow_schedule.py tests/test_cpp_native_test_timing.py tests/test_assessment_worker_archive.py` — 160 passed in 4.30 seconds.
- Separate affected regression invocation: 313 passed, 25 explicitly deselected with `-k 'not report and not exporter'`. No complete local export-suite pass is claimed. Hosted CI retains all prior tests and adds both new files without those exclusions.
- Python compilation, workflow shell syntax, fixed lock validation and `git diff --check` pass. Source subset was verified from the native GitHub source artifact, not represented as a complete repository checkout. Local Python 3.13.5 differs from hosted Python 3.11. Docker is unavailable locally; native execution must be established by hosted evidence.

Publication invalidates dependent tool-image, nested configuration, selected fixture and native execution proof. Unchanged legacy receipt reconstruction, source acquisition, timing validation, smaller profiles and earlier scoped evidence remain valid. New candidate CI, actual dependency download/build/linking, native v6 execution and independent complete review are pending; parent green workflows are not inherited.

## Retained real parent evidence

All 21 workflows on `934bcf6b` passed. C++ integration run `35854948193`, native job `107161838415`, used synthetic merge `8aa41110e1a20597f1088f1bc690dd2af8732eaf` with the exact parent tree, not a production release.

Source artifact `10747211116`: verified ZIP SHA-256 `384f179a69b574d4db2034e81580ff0295871ea90a5d58c9a7148c1608d9f3bd`, inner source archive `80d3af50da7c0d252dd32ec14870adaa054bcec3776de5be76d1a32bc9994ed8`. Native artifact `10747291327`: verified ZIP SHA-256 `830af7d3558e4ce9dc0d2aab735835338fbf019dd8db717dc2e6bbd36c25ea99`. Original result is `PASS_OWNED_PROJECT_INTEGRATION`, 53,761 ms, synthetic issuer true, production dispatch false, Bitcoin executed false, production qualified false.

Fresh replay with this increment reproduced both original canonical records exactly. Positive receipt `30e7861b42eb464864f166c9a485a424ab9371a2ef8784624f0999a63b51612c`, canonical `02312e25549e280e150e1089c2df0f1d719229ddf8ccebd76876f4fe587c44ad`; intentional-negative receipt `1f9bf052e7db4565e65d21ea4bdd7b89620c4bc6c351d6d9edd20697f5719bea`, canonical `81fc3216dce93d0d045e20bff064b631ad5f1af1b78bf59ce24eb0078d410e32`. These are replay/compatibility proofs, not a new native run. Parent English/es-MX engineering drafts remain unapproved owned-control artifacts, not Bitcoin reports.

## Acceptance matrix: no new whole-mission PASS

| Predicate | Current scoped proof and missing acceptance |
|---|---|
| C0 | Pinned target/public discovery retained. Meaningful frozen Bitcoin configuration, dependency closure and aggregate budgets remain unqualified. |
| C1 | Exact source/archive implementation and prior regressions retained. Complete required live Bitcoin acquisition through the path remains unproved. |
| C2 | Existing owned isolation proofs retained; new image/fixture and Bitcoin workload require native qualification. |
| C3 | Dedicated worker authority protections unchanged; final actual production issuer and release binding remain unproved. |
| C4 | Durable protocol evidence retained; full-profile real production dispatch/recovery acceptance remains outstanding. |
| C5 | Prior owned static analysis retained; new nested dependency control pending hosted execution; full required Bitcoin units not qualified. |
| C6 | Generic nested CMake implementation and regression proof added. Actual new native build/link/header results and Bitcoin component/dependency proof remain outstanding. |
| C7 | Prior owned tests/sanitizer replay/fuzz evidence retained; new fixture pending native execution; Bitcoin runtime scope remains unqualified. |
| C8 | Canonical observation/finding/disposition classes unchanged; actual Bitcoin results still required. |
| C9 | Original/generated/image headers and unit populations stay separate; no directory acceptance grants analyzed coverage by itself. |
| C10 | Scoring and assurance unchanged; no unknown metric or small-control pass becomes Bitcoin assurance. |
| C11 | Hard resource limits unchanged; Bitcoin-size aggregate runtime/memory/disk/retry/cost qualification not established. |
| C12 | Default controls preserved; fresh focused regressions pass; complete new hosted CI pending. |
| C13 | Prior owned bilingual report projection retained; actual Bitcoin structured outputs/PDF not produced. |
| C14 | Prior scoped mobile/WebKit proof retained; affected production bilingual/restart/mobile acceptance remains required. |
| C15 | Requester attestation, human/specialist approval, delivery and historical immutable artifacts unchanged. |
| C16 | Parent CI passed; new candidate CI and completed independent full base-to-head review remain mandatory. No author test is independent review. |
| C17 | No merge/deployment or production registry/profile activation. Exact frontend/backend/worker serving chain not established. |
| C18 | Actual authorized production Bitcoin assessment not executed. |
| C19 | Existing artifact identities/checkpoint retained; final report manifest and repeated immutable retrieval remain outstanding. |

## Exact next action

Publish the verified files on this same branch using a non-force update, verify remote blob identities, then inspect the actual new candidate native integration jobs and retained success/failure artifacts. Diagnose a failure at its first producer; do not weaken tests, increase budgets without measured justification, or blindly rerun. Record publication/check/run/artifact observations in the PR evidence summary without self-invalidating documentation-only commits.

After native control qualification, continue meaningful generic large-project execution/dependency/target coverage and qualified production-profile work. Obtain an independent review of the complete main-base-to-final-head diff, verify and resolve every material finding. Bitcoin qualification and actual authorized production acceptance remain distinct required stages. No rejected platform action may be bypassed; complete independently permitted work without inventing an exemption, new privilege or spending grant. Merge only after required implementation, review, checks and pre-merge qualification. The final SHIPPED declaration remains prohibited until every required predicate is evidenced.
