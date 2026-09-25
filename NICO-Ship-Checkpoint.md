# PR1641 continuation — durable owner liveness during long C++ execution

Continue the existing PR #1641 / `feat/cpp-full-project-capacity`. This descendant is based on `1bae247a9729512a809e3ec20930ae067680f7db`, tree `0cc831c0bbfa8499a995b7e47873155ca20b1866`; main/base last read `faaa10b037eb58e4175561b96dadf0d929764df4`. Preserve concurrent descendants; use non-force publication only. Do not push local source-export fixture history.

## Immutable continuity and governing contract

The complete previous checkpoint is preserved at [1bae247a:NICO-Ship-Checkpoint.md](https://github.com/BoneManTGRM/NICO/blob/1bae247a9729512a809e3ec20930ae067680f7db/NICO-Ship-Checkpoint.md). It retains cefff68f/3ff747f8 and all earlier evidence, repairs and original C0-C19 obligations. This is the sole active checkpoint. No requirement is waived by this summary.

Frozen Bitcoin: `bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`; 475 compiler contexts, 377 baseline tests, Debug wallet/tests/IPC and declared integration/sanitizer/fuzz scope remain. The distinct historical revision/run and all approved artifacts remain unchanged.

## Repairs now preserved

`cefff68f` corrected functional CSV membership/order and runtime receipt integrity. `9e71beb3` fixed the worker HTTP allowlist for `project-runtime-evidence`, with unchanged lease/hash/size protections. `1bae247a` provisioned the exact upstream-pinned previous-release v0.14.3 binaries required by wallet_ancient_migration, instead of removing that test. Licensing, bounded acquisition and no-execution provisioning remain intact.

Native integration run `36127119592` on 1bae247a has completed its contract and owned-project jobs. Downloaded owned artifact `10861400343`, 5,676,576 bytes, ZIP SHA256 `69c5e96f9c6d43915a47ea161996fcb26af3f88e9da7b8f7136e26b1b7db3a1c` was verified. It records VERIFIED_RUNTIME_DEPENDENCIES with the exact 24,644,309-byte archive/hash and retained member hashes. The built full-project image is `sha256:dfb699c4acf33c46fc45cdfb9d727e35e7be4ba307dbf4ae02abf5eece117cb8`; the owned receipt says PASS_OWNED_PROJECT_INTEGRATION and explicitly leaves production_qualified, bitcoin_executed and production_dispatch_exercised false. This proves real prerequisite provisioning and owned execution, not Bitcoin migration or production qualification. Its large qualification job `108052224324` was still active at the last observation and was not cancelled or duplicated.

## Reproduced durable-execution defect and correction

The configure-first wrapper passed the durable owner checkpoint only through result retention. Its probe used a separate local deadline callback during the actual long command, and did not pass the owner callback to the fresh static stage. Consequently a long build could run without renewing the at-most-300-second durable lease or observing cancellation; the retained earlier Bitcoin build lasted 752,128ms. The wrapper also validated the supplied remaining-time argument without enforcing it throughout execution.

The wrapper now combines the existing owner callback with an actual monotonic remaining-time deadline, including acquisition data, native execution, artifact retention and return. The probe calls that external checkpoint from its existing command polling and forwards it to the separately bounded static stage. Existing container cleanup remains unconditional after ownership loss; no lease, retry, native-command, CPU/RAM/scratch/process/time or network ceiling is increased.

A second reproduction showed a caught heartbeat failure could let an inner controller return and the consumer request another heartbeat, then publish a receipt. The existing owned=False state now irreversibly rejects re-entry for that consumer invocation. No receipt or failure mutation is sent after loss of authority; the server lease still independently fences the worker.

## Verification

Three real-wrapper/probe-seam regressions were observed failing for missing heartbeat, cancellation and remaining-time enforcement, then the identical three passed. Only the Docker boundary is substituted. The caught-heartbeat regression separately failed because the old consumer published after the caught conflict, then passed with the ownership latch. Two additional cases verify owner callback forwarding into the fresh static stage, including cancellation; these were added after the main RED/GREEN cycle and are not claimed as independent RED cases.

Fresh focused selection: 148 passed across wrapper/probe/static-stage/HTTP/jobs/baseline/contract/projection/selection files. A wider fresh selection including the entire consumer suite: 177 passed, one unchanged local Python 3.13 spawned-token PID-startup failure; that suite is not a complete pass. The failing fixture's two-second startup timing also failed before this correction. Its assertion/timeout remain unchanged; hosted Python 3.11 exact-candidate checks remain mandatory. Counts overlap and must not be added. All six changed Python files parse and their published Git blob hashes match tested local bytes. The evidence index is `docs/evidence/pr1641-owner-liveness-20260925/verification.json`.

## Whole-row acceptance

| Predicate | Status | Remaining requirement |
| --- | --- | --- |
| C0 | UNPROVEN | Full runtime prerequisites and aggregate qualification. |
| C1 | PASS, frozen native scope | Production inventory revalidation remains C18. |
| C2 | UNPROVEN | Complete combined workload isolation/capacity. |
| C3 | UNPROVEN | Final production owner/release/receipt chain. |
| C4 | UNPROVEN | Native long-job heartbeat/fencing/recovery and normal-intake completion. |
| C5 | UNPROVEN | Terminal static completion for every required context. |
| C6 | PASS, frozen baseline only | Retained 475 compiler contexts/generated inputs, not production proof. |
| C7 | UNPROVEN | Actual required migration, sanitizer and bounded fuzz scope. |
| C8 | UNPROVEN | Native/canonical/findings/register/report reconciliation. |
| C9 | UNPROVEN | Complete runtime/static/report populations and exclusions. |
| C10 | UNPROVEN | Actual score and assurance projections. |
| C11 | UNPROVEN | Measured combined workload within enforced budgets. |
| C12 | UNPROVEN | Generic C/C++ and supported-language production controls. |
| C13 | FAIL | Actual full-supported-scope Bitcoin structured output/PDF absent. |
| C14 | UNPROVEN | Final English/es-MX/mobile/progress/recovery acceptance. |
| C15 | UNPROVEN | Historical approvals preserved; eligible exact-edition delivery proof remains. |
| C16 | UNPROVEN | Final candidate checks and independent complete review. |
| C17 | FAIL | PR unmerged; final serving identities absent. |
| C18 | FAIL | No qualified normal-production Bitcoin assessment. |
| C19 | UNPROVEN | Actual bilingual artifact hashes/repeated retrieval/closeout. |

## Exact next work

Preserve the active 1bae native qualification and inspect its actual retained runtime outcomes. Qualify these owner-checkpoint changes on the final candidate. Verify sanitizer instrumentation/immutable execution identity, bounded fuzz replay/campaign/failure retention and measured capacity, not just flags or exit zero. Complete exact full-project image qualification/publication and independent review before merge/deploy; then obtain actual normal-intake production control and Bitcoin English/es-MX reports. No report or human approval may be synthesized.

The prior independent review quota exhaustion is not waived. Do not repeat an unchanged exhausted request, purchase credits, change accounts, or substitute author review for independence. No production enablement, merge, deployment, specialist approval or delivery authorization occurs in this correction. Do not declare SHIPPED without every mandatory whole-row proof.
