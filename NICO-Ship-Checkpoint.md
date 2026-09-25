# PR1641 continuation — runtime CSV and receipt integrity

Continue existing PR #1641 on `feat/cpp-full-project-capacity`; do not restart or replace it. This correction is based on candidate `3ff747f86943edd8be97ae05ce7b7d1cf33f0fac`, tree `65eb53650a7d61290de7bd48d5de52d2e4b061b8`; main/base remains `faaa10b037eb58e4175561b96dadf0d929764df4`. Recheck live refs and preserve concurrent descendants before any non-force publication. The local source export has no remote and is not a complete checkout; its fixture history must never be pushed.

## Immutable continuity and governing contract

This remains the sole active checkpoint. The complete prior checkpoint, including analyzer repairs, artifact transport, source/image identities, accepted maintenance and the older evidence chain, is retained at [3ff747f8:NICO-Ship-Checkpoint.md](https://github.com/BoneManTGRM/NICO/blob/3ff747f86943edd8be97ae05ce7b7d1cf33f0fac/NICO-Ship-Checkpoint.md). Its records and all stronger original C0–C19 requirements remain binding; this summary does not erase or relabel them.

Frozen Bitcoin qualification remains `bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`, all 475 compiler contexts, 377 baseline tests, Debug wallet/tests/IPC and generated/header evidence. The distinct historical revision `0e9018e8b65611b0769545e177110e4b7fc51244` and run `comprun_7cc47a5a81695fa452354479ea23b422` remain unchanged. No source population, test, sanitizer, corpus member, analyzer rule, runtime command, isolation setting, resource limit, authority or human approval was removed or relaxed by this correction.

## Verified current native failure

Hosted integration run 36117852901 at source `7c084721ea24754680aefbabd5c0736ecd43f5ad` completed its contract and owned-control jobs successfully, then failed qualification job 108018383610. Artifact 10858291369 is 12,179,656 bytes; ZIP SHA256 `b1dea2df91dd9fcf376f039c59d818a602e674690f6a0ab733d6442923291fd3` was verified before inspection.

The retained probe proves 377/377 baseline tests passed, 475/475 compiler contexts checked, generated-context and boundary verification, and cleanup. Functional execution returned exit 0 but its actual CSV contains four Passed rows and two Skipped rows (`interface_ipc.py`, `wallet_ancient_migration.py`). The runtime controller rejected presentation order with `worker_runtime_functional_results_invalid`; runtime qualification, sanitizers, fuzz and later static execution are not established by this run. Preserve the original failed receipt.

The frozen upstream runner sorts results by status/name before writing CSV, whereas NICO compared row order with selection order. Separately, the selected wallet migration test requires previous-release v0.14.3 binaries. The latest head adds pinned pycapnp for IPC, but that image/runtime repair still needs native qualification. Do not replace either skipped test with an easier test or count skipped tests as executed.

## Implemented corrections and tests

1. Functional CSV reconciliation validates exact unique test membership independently of presentation order, projects outcomes in the original selected order, excludes Skipped rows from executed membership, and rejects malformed/contradictory totals and invalid durations. The CSV reproduction first yielded 11 expected failures and 3 passing controls, then 14 passes.
2. Runtime evidence validation reconstructs every fixed semantic command, UID, environment and working directory from the declared plan and release-owned options; it requires every corpus replay exactly once, valid read outcomes, bounded exit codes and per-operation/cumulative timing. Previously, deleting every fuzz replay or changing commands/identities could retain completion. The binding reproduction first yielded 18 expected failures and 3 passing controls, then 21 passes.

The 35 new regression cases are included in the existing `tests/test_cpp_runtime_execution.py` already named by CI; its four original tests are unchanged. Final affected selection: 172 distinct cases passed, zero failures/errors/skips, including all 39 runtime cases, contract/projection/worker/baseline/configuration and workflow interruption neighbors. The complete 47-file local C++ command exceeded the 120-second command limit after partial progress and has no terminal result; it is not credited. Local Python 3.13 differs from hosted Python 3.11. No native execution or independent review is claimed from synthetic Docker-boundary tests. Exact commands, hashes and RED/GREEN counts are in `docs/evidence/pr1641-runtime-integrity-20260925/verification.json`.

## Remaining whole-mission acceptance

| Predicate | Current status | Evidence still needed for the whole row |
| --- | --- | --- |
| C0 | UNPROVEN | Complete runtime prerequisites, scope and aggregate qualification. |
| C1 | PASS (historical native scope only) | Retain complete immutable inventory; production revalidation remains C18. |
| C2 | UNPROVEN | Entire combined workload isolation/capacity, not only baseline controls. |
| C3 | UNPROVEN | Final production worker/release/receipt authority chain. |
| C4 | UNPROVEN | Actual normal-intake durable full-scope completion/recovery. |
| C5 | UNPROVEN | Terminal substantive static completion for every required context. |
| C6 | PASS (frozen native baseline only) | 475 compiler contexts and generated inputs retained; not production proof. |
| C7 | FAIL | Resolve required functional skips and complete sanitizer/fuzz runtime proof. |
| C8 | UNPROVEN | Actual native/canonical/finding/register/report reconciliation. |
| C9 | UNPROVEN | Complete static/runtime/report populations and exclusions reconciled. |
| C10 | UNPROVEN | Actual final score inputs and maturity/assurance separation. |
| C11 | UNPROVEN | Combined workload fits enforced stage and aggregate resource budgets. |
| C12 | UNPROVEN | Qualified generic C/C++ and supported-language production controls. |
| C13 | FAIL | Actual full-supported-scope Bitcoin structured outputs and PDF absent. |
| C14 | UNPROVEN | Final English/es-MX, mobile, progress and restart/retrieval acceptance. |
| C15 | UNPROVEN | Preserve historical approval; verify eligible exact-edition one-action delivery. |
| C16 | UNPROVEN | Fresh complete candidate CI/security and independent full-diff review. |
| C17 | FAIL | PR unmerged; final frontend/backend/worker serving identities absent. |
| C18 | FAIL | No qualified normal-production Bitcoin run for this candidate. |
| C19 | UNPROVEN | Final bilingual artifact hashes, repeated retrieval and closeout index. |

## Exact next work

Verify the published candidate against this correction and inspect its automatically queued checks without cancelling or duplicating active qualification. Provision and verify the frozen functional-test prerequisites without removing required scope. Validate real sanitizer instrumentation/binary identity, bounded replay/campaign populations, failure retention and measured combined capacity; command flags and zero exits alone are insufficient. Reconcile the terminal full-scope native receipt with normal production selection, immutable worker image, canonical outputs and bilingual rendering. Complete independent full-range review and final checks before merge/deploy, then verify actual production control and Bitcoin reports. Image publication remains distinct from production qualification.

Prior independent-review allowance exhaustion is not waived: do not repeat an unchanged exhausted request, purchase credits, change accounts, substitute author review or invent approval. No merge, deployment, production activation, client-delivery authorization or human/specialist attestation was performed by this correction. Do not issue the SHIPPED declaration until every mandatory whole-row predicate passes.
