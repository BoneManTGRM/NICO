# Active mission: Comprehensive C/C++ and Bitcoin qualification

Continue PR #1641 on `feat/cpp-full-project-capacity`. The owner's `NICO-CPP-Bitcoin-Execution-Prompt.md` and C0-C19 contract remain governing. Same-branch non-force corrections and gated merge/deployment are authorized. No replacement PR, new privileges/spending, platform bypass, automated human approval or unsupported completion claim.

## Current correction and continuity — 2026-09-23

Publication parent `370997c19163717c0abeeddafe19ba8b9e32ebf0`, tree `959e6778a8e4636be65b4b11cbb66c0546936d14`; observed main/base `faaa10b037eb58e4175561b96dadf0d929764df4`. Resolve the new enclosing SHA from GitHub; do not add a self-referential documentation-only commit.

The complete prior checkpoint remains immutable at [370997c1](https://github.com/BoneManTGRM/NICO/blob/370997c19163717c0abeeddafe19ba8b9e32ebf0/NICO-Ship-Checkpoint.md), blob `7770265538e3704404d043ae1de1989da04aae52`. It retains detailed nested-CMake/dependency implementation, RED/GREEN evidence, original native receipts/program hashes, C0-C19 and the complete 934bcf6b/0b9d7038/PR1627 checkpoint chain. No historical evidence or denied-operation record is removed or rewritten; there remains one active ledger. Historical next-action text is not a current instruction to restart.

Target remains `bitcoin/bitcoin@bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`. Historical report revision `0e9018e8b65611b0769545e177110e4b7fc51244`, run `comprun_7cc47a5a81695fa452354479ea23b422`, is separate. Production entrypoint `https://app.nicoaudit.com`; no Bitcoin execution or release observation is asserted here.

## BOOST-EXACT-1: actual native failure and smallest repair

Run `35861027079`, contract job `107181001680`: **498 passed, 37 warnings in 85.53 seconds**, including all configured exporters and new regression files. Existing syntax/deprecation warnings remain; no warning-free/full-repository pass claim. Source-export and LLVM-inventory jobs passed.

Native job `107183029346` actually failed at all three CMake configure stages, before project build/static analysis/sanitizer execution. Retained artifact `10750147508`, 63,367 bytes, was downloaded and ZIP SHA-256 verified: `3c1c582880a1f2135dd6f7048f07187281068d8852808f93040a2b9ab4940121`. Its native receipt and persisted canonical result preserve the failure. Overall control remained UNPROVEN, 8,048 ms. The later `configuration_aware_static_analysis_incomplete` assertion is a consequence, not the root cause.

First incorrect producer: the owned fixture requested `find_package(Boost 1.74 EXACT CONFIG REQUIRED)` against pinned Boost configuration version `1.74.0`. Native CMake explicitly rejected that abbreviated exact version. Repair only the requested fixture version to `1.74.0`, preserving `EXACT CONFIG REQUIRED`, dependency use/link/runtime checks, every native assertion, failed evidence, budgets and permissions. The existing string test encoded the same incorrect abbreviation; correct its expectation and add a test deriving the full requested upstream version from the pinned package lock.

Native package retrieval, all SHA-256 checks, extraction and tool-image construction succeeded. Image config `sha256:b983d8f4e2a5c5ec98ba172d03f6620597be6534586bfa883df28a7aed31c3ed` belongs to the failed-control run, not qualified production. The separate positive fuzz branch completed 128 tool-reported executions; it does not satisfy failed project build/static/sanitizer predicates. Do not republish a registry image or relabel the failed run as passing.

Reproduction: two expected test failures / 26 controls passed. Fresh repaired publication command: `python -m pytest -q tests/test_cpp_project_dependencies.py tests/test_cpp_nested_cmake.py tests/test_cpp_fixture_tree.py tests/test_cpp_fuzz_tool_provisioning.py tests/test_cpp_integration_workflow_schedule.py tests/test_cpp_native_test_timing.py tests/test_assessment_worker_archive.py` — **161 passed in 4.03 seconds**. Python compilation and `git diff --check` pass. Local Python 3.13.5 differs from hosted 3.11; Docker is unavailable locally. New native execution is required, not inherited from tests.

Invalidation: fixture/source/configuration identity and all dependent native proof change. Fixed dependency lock/tool recipe, production implementation, old v1-v5 programs and their prior exact receipt reconstruction remain unchanged. New candidate full CI and independent review are pending; no author test is an independent complete review.

## Retained implementation and evidence

Published 370997c1 contains real opt-in configuration v6 for canonical nested CMake working directories, source-bound private analyst recompilation and reconstruction. Existing v1-v5 and their embedded programs remain byte-identical. Fixed Boost 1.74.0 and SQLite 3.40.1 input provisioning uses exact official Debian metadata, hashes and lengths, 16 MiB aggregate input bound and 30-second aggregate download budget; actual retrieved inputs total 11,371,836 bytes. Offline extraction runs no package install hooks. No assessed source enters tool-image construction or receives runtime networking.

The owned nested library uses Boost headers and calls SQLite, with exact header/runtime-version checks. Source/generated/tool-image header populations, both sanitizer binary replays, bounded fuzz, intentional negative failures and bilingual engineering drafts remain required. Default smaller controls are preserved. The existing workflow retains all tests, contents-read-only permissions and five-minute job bounds. Worker class stays 2 CPU/2 GiB/256 PID, one-attempt 180-second control, private credentials/authority and approval boundaries unchanged.

Earlier timing validation, atomic archive acquisition, durable leases/receipts/restart, Spanish fixes and human approval/delivery/history protections remain. Real parent 934bcf6b owned run `35854948193`, native job `107161838415`, verified source artifact `10747211116` (ZIP `384f179a69b574d4db2034e81580ff0295871ea90a5d58c9a7148c1608d9f3bd`) and native artifact `10747291327` (ZIP `830af7d3558e4ce9dc0d2aab735835338fbf019dd8db717dc2e6bbd36c25ea99`) remain valid only for their original inputs. Both original receipts reconstruct exactly with the new production source. They are synthetic-issuer owned proofs, not Bitcoin, actual production OIDC or approved client reports.

## Acceptance matrix — no new whole-mission PASS

| Predicate | Current scoped evidence and missing acceptance |
|---|---|
| C0 | Pinned discovery retained; meaningful frozen Bitcoin configuration/dependency closure and aggregate budgets unqualified. |
| C1 | Exact acquisition/archive implementation retained; actual complete required Bitcoin acquisition unproved. |
| C2 | Prior owned isolation proofs retained; corrected nested fixture and Bitcoin workload need native qualification. |
| C3 | Worker authority protections unchanged; final production issuer/release binding unproved. |
| C4 | Durable protocol/restart evidence retained; full-profile production dispatch/recovery outstanding. |
| C5 | Prior owned static proof retained; new native build blocked by exact-version fixture defect; Bitcoin required units unqualified. |
| C6 | Nested implementation and pinned packages/image built; corrected native project linking/header proof and Bitcoin components outstanding. |
| C7 | Prior owned sanitizer/fuzz proof retained; failed run's separate fuzz success is not build/sanitizer success; Bitcoin runtime scope unqualified. |
| C8 | Observation/finding/disposition identities unchanged; actual Bitcoin results required. |
| C9 | Unit/source/generated/image-header populations stay separate; no scheduling or package install becomes coverage. |
| C10 | Score/assurance behavior unchanged; no Bitcoin assurance inferred from owned controls. |
| C11 | Resource ceilings unchanged; Bitcoin runtime/memory/disk/retry/cost qualification unproved. |
| C12 | Default controls preserved; 498 parent configured tests and 161 repaired focused tests pass; new complete CI required. |
| C13 | Prior owned bilingual path retained; actual Bitcoin structured/PDF output not produced. |
| C14 | Prior mobile/WebKit evidence retained; affected production bilingual/restart/mobile acceptance outstanding. |
| C15 | Authorization, specialist/operator approval, delivery and immutable history unchanged; actual human-only actions remain human-only. |
| C16 | No completed independent full review observed. New candidate CI/review and material-finding disposition mandatory. |
| C17 | No merge, deployment, production registry/profile activation or exact serving-chain proof. |
| C18 | Authorized production Bitcoin assessment not executed. |
| C19 | Failed/native/source artifacts and one checkpoint retained; final report manifest and repeated retrieval outstanding. |

## Exact next action

Publish this correction as a non-force descendant of 370997c1 after checking remote blob identities; inspect the new automatic native integration and retained artifacts. Diagnose the first actual producer failure, preserve failed receipts, and do not blindly rerun, weaken assertions or change budgets without measured justification. Record publication/run observations in the PR without self-invalidating documentation commits.

Then continue meaningful generic large-project configuration/dependency/target coverage and qualified production-profile work. Obtain independent complete base-to-final-head review and resolve each material finding. No denied platform operation may be bypassed, no new authority invented, and no required Bitcoin scope silently reduced. Merge only after required implementation, review, checks and pre-merge qualification; verify coordinated frontend/backend/worker deployment and actual authorized bilingual production Bitcoin report afterward. The SHIPPED declaration remains unavailable until every mandatory predicate has evidence.
