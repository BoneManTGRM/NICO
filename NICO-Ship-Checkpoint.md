# PR1641 continuation — runtime transport and required prerequisites

Continue the existing PR #1641 / `feat/cpp-full-project-capacity`. This candidate descends from `9e71beb31bb1cc7c7c78d7e6af1cfafd271e5119` (tree `517c343e37056d03028c36c92413a5618d949857`); main/base last read `faaa10b037eb58e4175561b96dadf0d929764df4`. Recheck refs before non-force publication and preserve concurrent descendants. The local exact-source export is a subset, has no remote and must never be pushed as repository history.

## Immutable continuity and governing scope

The complete preceding ledger and its original C0-C19 contract are retained at [cefff68f:NICO-Ship-Checkpoint.md](https://github.com/BoneManTGRM/NICO/blob/cefff68f4a06c75e6a210c4770ae9f170bd21cac/NICO-Ship-Checkpoint.md), including the earlier 3ff747f8 checkpoint and predecessor chain. This is the sole active checkpoint; this update does not remove older proof or waive acceptance.

Frozen Bitcoin remains `bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`, with 475 compiler contexts, 377 baseline tests and the selected Debug wallet/tests/IPC scope. Historical revision `0e9018e8b65611b0769545e177110e4b7fc51244` and run `comprun_7cc47a5a81695fa452354479ea23b422` are unchanged. No selected functional test, sanitizer, corpus member, analyzer rule, execution command, resource envelope, approval control or human decision is removed by this prerequisite repair.

## Published runtime transport correction

Commit `9e71beb31bb1cc7c7c78d7e6af1cfafd271e5119` adds the already-backend-supported `project-runtime-evidence` key to the worker HTTP allowlist. The former producer rejected that key before upload. Existing lease identity, hashes, gzip/raw byte limits and unknown-key rejection are unchanged. Five HTTP-boundary cases include the failing runtime case and passing static/unknown-key controls. Recorded RED: one failure/four passes; identical GREEN: five passes. HTTP/durable-job suites: 48 passes; two existing encoding/size controls also pass. A wider 77-case local attempt had one unchanged spawned-process PID-startup failure on Python 3.13; that attempt is not a full pass. Exact-head hosted qualification remains required.

## Latest native failure narrows the prerequisite gap

Integration run `36119915548`, source `3ff747f86943edd8be97ae05ce7b7d1cf33f0fac`, retained artifact `10859117522` (ZIP SHA256 `f4688db5d32bc58ccf7c5cdb0c38d7084404e41a55c00db47c1667a374fdabb9`) was downloaded and hash-verified. The probe retains 377 passing baseline tests, 475 checked compiler contexts and verified generated inputs/boundary/cleanup. Its actual functional CSV has five Passed rows: feature_shutdown, interface_ipc, mempool_datacarrier, p2p_seednode and rpc_openrpc; wallet_ancient_migration is Skipped. This proves the pinned pycapnp repair allowed IPC execution in this run, not complete runtime qualification. Preserve the original failure; the older four-pass/two-skip run remains historical.

The upstream v0.14.3 migration test uses old/new disposable nodes and explicitly requires previous releases. The pinned upstream test framework discovers the release directory from `PREVIOUS_RELEASES_DIR`. Its `get_previous_releases.py` binds the x86_64 Linux archive to SHA256 `706e0472dbc933ed2757650d54cbcd780fd3829ebf8f609b32780c7eedebdbc9`; the official release directory reports 24,644,309 bytes.

## Implemented prerequisite repair

A reviewed release-owned dependency lock and bounded provisioning controller acquire that exact archive and copy only the required bitcoind/bitcoin-cli members plus the unchanged upstream MIT license. Downloads use HTTPS with no redirect or ambient credential environment; exact archive size/hash precede parsing, decompression/member/count/path limits apply, selected symlinks/duplicates/traversal/missing inputs reject, and existing output cannot be overwritten. The controller never runs a downloaded binary. It retains lock/archive/member/license identities and explicit failure receipts.

Both existing full-project image build paths invoke the same provisioner. The no-network Docker build verifies member hashes, puts immutable test dependencies in `/opt/nico-runtime`, and sets `PREVIOUS_RELEASES_DIR` for the isolated runtime. Native assessment commands and selected tests remain unchanged. Provisioning remains outside assessed execution; legacy binaries will run only inside the existing disposable, credential-free, no-external-network assessment boundary. No real funds, live peers, real wallets or keys are used.

Local verification: the new positive extraction/hash/retention test was recorded failing against the UNPROVEN scaffold, then passed after implementation. The final prerequisite suite has 18 passes including malformed archive, URL/path, license, overwrite and workflow/image binding controls. The disjoint dependency/tool/runtime neighbors have 105 passes. A fresh combined run passed all 123 cases; all 14 workflow shell blocks and both new Python ASTs validate. This is synthetic archive/transport evidence, not a real v0.14.3 download, image build, migration execution or independent review. The new image invalidates prior image qualification and must pass the existing owned prerequisite before large execution.

## Whole-row acceptance remains evidence-based

| Predicate | Status | Required remaining proof |
| --- | --- | --- |
| C0 | UNPROVEN | Complete runtime prerequisites and combined qualification. |
| C1 | PASS, frozen native scope | Preserve complete inventory; production revalidation is C18. |
| C2 | UNPROVEN | Complete workload isolation/capacity, beyond baseline controls. |
| C3 | UNPROVEN | Final production worker/release/receipt authority chain. |
| C4 | UNPROVEN | Normal-intake full-scope completion/recovery. |
| C5 | UNPROVEN | Terminal substantive static completion of every required context. |
| C6 | PASS, frozen native baseline | 475 compiler contexts and generated/header proof, not production. |
| C7 | FAIL until native proof | Wallet prerequisite execution plus sanitizer/fuzz qualification. |
| C8 | UNPROVEN | Actual native/canonical/register/report reconciliation. |
| C9 | UNPROVEN | Complete static/runtime/report populations and exclusions. |
| C10 | UNPROVEN | Actual score inputs and maturity/assurance distinction. |
| C11 | UNPROVEN | Combined measured workload within enforced budgets. |
| C12 | UNPROVEN | Generic C/C++ and supported-language production controls. |
| C13 | FAIL | Actual full-supported-scope Bitcoin structured report/PDF absent. |
| C14 | UNPROVEN | Final English/es-MX/mobile/progress/recovery acceptance. |
| C15 | UNPROVEN | Historical approval preserved; eligible exact-edition one-action proof remains. |
| C16 | UNPROVEN | Final candidate CI/security and independent complete review. |
| C17 | FAIL | PR unmerged; final serving identities not established. |
| C18 | FAIL | No qualified normal-production Bitcoin run for this candidate. |
| C19 | UNPROVEN | Actual artifact hashes/repeated retrieval/closeout index. |

## Exact next work

Publish the verified prerequisite descendant, then preserve existing automatic qualification and inspect actual retained native outcomes. Do not cancel or duplicate active jobs for reassurance. Prove the required wallet test rather than replacing it; retain any actual native failure. Complete sanitizer instrumentation/binary identity, bounded fuzz replay/campaign evidence, failure retention and measured capacity. Qualify and publish the exact full-project worker image, not the historical standalone image. Complete final independent review/checks before merge/deploy and then actual production control/Bitcoin report acceptance.

Prior independent-review allowance exhaustion is not waived: no unchanged repeated request, purchased credits, alternate account, author-review substitution or fabricated approval. No production enablement, merge, deployment, specialist approval or client-delivery authorization is performed by this correction. The final SHIPPED declaration still requires every mandatory whole-row predicate.
