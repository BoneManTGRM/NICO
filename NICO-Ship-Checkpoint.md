# PR1641 continuation — recover executable analyzer after placeholder corruption

Continue the existing `feat/cpp-full-project-capacity` branch and PR #1641. Immediate parent observed: `4b44ed16e24965441f8e8153f538093b20f572e1`, tree `46b10568b350bceee3dba11b6a0b77fdf3dc3f9f`; main/base `faaa10b037eb58e4175561b96dadf0d929764df4`. The original NICO-CPP-Bitcoin-Execution-Prompt.md and stronger current C0-C19 contract remain mandatory. This is an executable-source recovery, not full capability, merge, deployment, independent review, or approval.

## First incorrect layer and bounded recovery

The live GitHub compare from `95f34b5324df6f17f2ab2c72efa7d67d00c9d2b3` to `4b44ed16e24965441f8e8153f538093b20f572e1` contains only one changed path: `nico/assessment_cpp_project_static.py`, 476 lines removed and one added. The first intervening commit wrote `placeholder`; the second wrote literal `see-local-file`. Despite the latter commit title, no compiler-predefine or dependency-model implementation was present. A direct file read returned blob `5c73c5cb53073db7b2c31b81140bd702546045a9` with exactly that text.

Restore the complete executable module byte-for-byte from `95f34b5`, Git blob `4f9ec0a9c867c874ca862a2a291e5e23a93104b9` (28,891 bytes). Preserve all other current files and both intervening commits in history; publish a non-force descendant rather than resetting the branch. The source was reconstructed from authoritative artifact10803019659: ZIP SHA256 `a268781686d43bcceb3eb01ff2e01295603b17932fbdbbb57822769f21dfaecb`, inner archive SHA256 `82544ce4fde84a339e61da62259f230e5ece827e2f59d21f424ab9143f7420f5`, source tree `2c02d26cb96a051c6f40c7ebcbdcaf20d0f616fc`. The CI merge export is not a production merge. No local export-fixture history is published.

Recorded RED with the actual broken text: `python -m pytest -q tests/test_cpp_project_static.py` produced39 failures/2 passes, exit1. Import raises NameError for `see`; producer-ordering assertions also fail. Identical command after restoring the exact module:41 passed, exit0. Broader unchanged four-file selection (static, static-stage, compiler-budget-v2, preprocessing-truth):125 passed, exit0. Counts overlap and are not additive. RED log SHA256 `17adc7a2b2a8b97811289a7d01de8d01cc61cce34d54f364bb20569b856b5815`; same-command GREEN `2f4732c586995104aa071102838621cbfe536f747d36a0e7427909f1c6593a0d`; broader GREEN `256b6cb7b87e199ad95421956704040a06ea819a36f2de47cb8c518d8936e612`. These are local contract tests, not hosted qualification or independent review. One existing SyntaxWarning occurred in RED.

GitHub's existing non-force ref-update action successfully checked the unchanged current head. Source publication is available in this session. Local Git network access cannot resolve github.com; authenticated connector operations remain the publication route. Do not treat that local network result or an older support incident as a universal blocker.

## Retained execution and actual remaining dependency

Frozen Bitcoin stays `bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`, compilation database `fc89aa69b2a369417cbff01d2784225bd23547827b1f7fd946669f919526aa1b`.

Retain run35978926706/job107568329757/artifact10800637897: complete3,248 inventory entries/3,031 files/49,729,651 bytes; build passed;377 native tests executed/passed with zero skipped;121 generated members/32,033,843 raw bytes;475/475 compiler-v2 contexts;406 original and92 generated compiler-visited headers. Static attempted475 but the corrected parser supports only2 completed contexts and167 unreviewed candidates.429 preprocessing errors are limitations, not code-risk findings. Raw evidence and historical reports remain unchanged. ZIP SHA256 `80c977ed121797428e6547bffcacf6b7551978074e9e084596330b83bcd8ea69`; static native `b46607d23bd87a969c772dc071d54d9c88e97db37f50b119bf787d14682ea65a`.

The published parser correction, exhaustive analysis depth, versioned600-second compiler budget,90-second/context/four-worker bounds,1,800-second parent, separate600-second static stage,4CPU/12GiB/no-swap/256PID/9GiB limits and required populations are retained. Restoring the module does not solve missing compiler-predefine and dependency/model input handling. The earlier owned native reproduction demonstrates that both inputs matter and that adding every system-header directory is not an adequate correction. Recover conversation artifact NICO-PR1641-95f34b5-environment-evidence.zip and the exact pinned analyzer in artifact10804136344; validate against the producer before implementation.

## C0-C19 whole-row status

| Predicate | Status | Scope or missing proof |
| --- | --- | --- |
| C0 | UNPROVEN | Live refs/authority/frozen target recovered; complete runtime scope/budgets remain. |
| C1 | PASS | Retained complete immutable qualification inventory/acquisition. |
| C2 | UNPROVEN | Retained isolation/cleanup; complete production workload remains. |
| C3 | UNPROVEN | Final full-workload identity and authority binding remains. |
| C4 | FAIL | Full project evidence still not integrated through normal durable production completion. |
| C5 | FAIL | Compiler/environment modeling is unfinished;475 required static contexts not completed. |
| C6 | PASS | Retained native baseline/generated/compiler/header qualification; no input change here. |
| C7 | UNPROVEN |377 baseline tests passed; declared integration/sanitizer/fuzz scope remains. |
| C8 | UNPROVEN | Truth correction retained; actual canonical/report reconciliation remains. |
| C9 | UNPROVEN | Baseline/compiler population proof retained; full static/runtime/report proof remains. |
| C10 | UNPROVEN | Scoring unchanged; final new-run assurance projection remains. |
| C11 | UNPROVEN | Successful full-analysis and combined runtime capacity not yet qualified. |
| C12 | UNPROVEN |125 affected local cases pass; complete current qualification remains. |
| C13 | UNPROVEN | Actual complete-scope Bitcoin report absent. |
| C14 | UNPROVEN | New bilingual/mobile/progress/recovery acceptance absent. |
| C15 | UNPROVEN | Approval/history controls untouched; final eligible one-action proof remains. |
| C16 | FAIL | Native completion, final checks and independent review remain. |
| C17 | FAIL | PR unmerged; no new production serving identities. |
| C18 | FAIL | No actual full-capability production Bitcoin run. |
| C19 | UNPROVEN | Final bilingual artifacts/hashes/repeated retrieval absent. |

No operator approval, delivery authorization, deployment, new spending/privilege or review waiver. Prior Codex review request5802036311/reply5802038248 exhausted its allowance; no unchanged retry or account switch. Author verification is not independent review.

EXACT NEXT ACTION: verify publication of the recovered module, then implement the generic compiler-predefine/dependency input correction against the existing clean/diagnostic/missing-header native controls. Preserve every475-context target and do not silence preprocessing errors. Continue canonical worker/report integration and declared runtime scope while automatic qualification runs, then complete independent review, gated merge/deployment and real bilingual production acceptance. Do not issue SHIPPED before all mandatory rows pass.

## Immutable continuity

Full predecessor ledger: `95f34b5324df6f17f2ab2c72efa7d67d00c9d2b3:NICO-Ship-Checkpoint.md`. Its533d/3652/2195/a561/cbecc/fd1/254/b609/d236/a10/abb/1ebc chain preserves the original contract, merged PR1627, native successes/failures, source/tool/control identities, worker/database evidence and approval history. Historical revision0e9018e8b65611b0769545e177110e4b7fc51244/runcomprun_7cc47a5a81695fa452354479ea23b422 stays unchanged. This is the sole active ledger.
