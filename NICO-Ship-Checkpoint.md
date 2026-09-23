# Current continuation — pinned Cap’n Proto for actual Bitcoin configuration

Continue the same PR #1641 and branch. Publication parent is `99fe635f7988576d7a6e982fa097619cabac0849`, tree `283e8933ef82991c62751c4fccd5d69b46baefdc`. No replacement branch, merged/deployed claim, production activation, or human approval.

## CAPNP-1: actual failing producer and bounded correction

Run `35885476817`, native job `107265776249`, artifact `10761704921` (verified downloaded ZIP SHA-256 `363c6fb057d63cc8c68994d210936c817ebce03137e5f9e8e303ee0a23d2313c`) completed the owned controls and the frozen Bitcoin checkout. Actual isolated configuration exited 1 after 7,647 ms because `src/ipc/libmultiprocess/CMakeLists.txt:18` required missing Cap’n Proto. Boundary and cleanup verified; the failed receipt stays UNPROVEN.

The exact target’s `depends/packages/native_capnp.mk` pins upstream Cap’n Proto 1.5.0 archive SHA-256 `77dbc13ca82d9c87ddb4581dd49559d45b63096433d3dadea08b7f31b360a5ba`. The existing provisioner gains one fixed source-input mode, with the same nonredirecting credential-free HTTPS and hash checks, atomic UNPROVEN retention and no install hooks on the controller. A 4 MiB archive ceiling plus all nine existing package inputs is 16,406,280 bytes, within the existing 16 MiB combined input ceiling. Source downloading is separately bounded at 30 seconds; the old project/LLVM mode budgets and identities are unchanged.

The offline multistage image builds only this pinned upstream dependency, with two compiler jobs and a 180-second build-command ceiling. It retains exact source lock and receipt, installs static/PIC libraries and tools, checks the tool’s 1.5.0 version, and leaves the previous final-stage recipe intact apart from copying the verified build outputs. The enclosing image-build timeout remains 210 seconds and every workflow job remains five minutes. These are enforced bounds, NOT claims that native preparation will finish within them. Local Docker and source downloads are unavailable; actual image build and Bitcoin configure must be verified by hosted evidence.

IPC is now explicitly ON and must appear as a typed cache value. Wallet/tests stay ON; the frozen commit/tree, original inventory and prior explicit GUI/benchmark/ZeroMQ exclusions are unchanged. No alternative Bitcoin revision, reduced source population, worker-resource increase or report/receipt truth change.

## Verification and exact next action

Baseline affected package suites: 56 passed. New source-mode tests initially failed because the capability and pin were absent; 17 new tests pass after repair, including rejected substitutions, hash/size failures, interruption retention and the combined input budget. Fresh affected publication command: 92 passed in 5.10 seconds, without excluding tests from the selected files. The complete configured local invocation was attempted but stopped at the 180-second execution limit before completion; it is NOT a passing suite. The unchanged full hosted command includes every former file plus the new suite. AST, workflow shell syntax, read-only permissions, five-minute job bounds and diff checks pass.

Publish only as a non-force descendant after verifying current head and each blob. Inspect the automatically triggered dependency image and real Bitcoin configuration. Preserve the actual first failure rather than retrying unchanged inputs, dropping IPC or weakening assertions. Once real configuration is captured, continue the remaining required whole-scope analysis/build/unit/integration/sanitizer/fuzz execution, measured resource qualification, production worker/profile, independent complete review and protected production report. The full C0-C19 contract in the retained checkpoint chain remains mandatory; no full-capability SHIPPED claim is supported yet.

## Exact historical continuity

The entire previous active checkpoint is preserved verbatim at [99fe635f](https://github.com/BoneManTGRM/NICO/blob/99fe635f7988576d7a6e982fa097619cabac0849/NICO-Ship-Checkpoint.md). Its SHA-256 is `c1393d72378a5b188f1d6c661a4c3b4897a7357f18b59bbb147bb3dbf1d3560e`, Git blob `4c409f030423878b42c1fa6f6111d73b168fe4c7`, length 9902 bytes, also retained at the immutable publication parent. Historical success, failures and restrictions remain scoped to their original inputs.


The governing target remains `bitcoin/bitcoin@bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`. Historical target/run and all prior approvals remain separate. Merge only after required implementation, Bitcoin qualification and independent full-range review. Actual coordinated frontend/backend/worker release identity, bilingual production Bitcoin report and protected approval/retrieval remain required afterward. Do not bypass genuine platform restrictions or fabricate evidence.
