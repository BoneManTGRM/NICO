# Active mission: Comprehensive C/C++ and Bitcoin qualification

Updated 2026-09-23. Continue PR #1641 on `feat/cpp-full-project-capacity`; do not create a replacement branch or PR. The owner's `NICO-CPP-Bitcoin-Execution-Prompt.md` and its C0-C19 acceptance contract remain governing. This is a continuation, not a new strategy.

## Historical evidence is preserved, not superseded by a new success claim

The complete previous checkpoint is retained verbatim in the immutable parent:

[Full previous checkpoint at 0b9d7038](https://github.com/BoneManTGRM/NICO/blob/0b9d7038d7558fd478aad8c32ea871c765b429f1/NICO-Ship-Checkpoint.md).

Its Git blob is `ff2a3d2f7d6e89fbf100763158d4b9b16ab29271`, SHA-256 `b8109fcc5efbd3c93e1450e953599d2dcd7bac8f235e9b155cbc5e6d4d6816ec`, length 589,918 bytes. Follow that exact version for earlier PR #1627 worker protocol, database/restart, registry, authorization, truth-stress, production and approved-report evidence. Those historical receipts and accepted scoped proofs are not erased, rerun, or promoted to current full-project acceptance. This shorter current checkpoint separates today's state from stale historical next-action instructions; there is still only one active checkpoint.

## Immutable anchors for this increment

- Repository: `BoneManTGRM/NICO`.
- Observed base/main: `faaa10b037eb58e4175561b96dadf0d929764df4`.
- Parent candidate: `0b9d7038d7558fd478aad8c32ea871c765b429f1`.
- Parent tree: `683898616480ed13da69e917205d1d30356fea62`.
- Parent integration merge: `75440faf4c06bd7b6044f2a69cad580a8bcff115`, with the same tree. This is a CI merge identity, not a production release.
- Qualification target: `bitcoin/bitcoin@bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, recorded tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`.
- Historical report target remains separate: `0e9018e8b65611b0769545e177110e4b7fc51244`, run `comprun_7cc47a5a81695fa452354479ea23b422`.
- Production entrypoint: `https://app.nicoaudit.com`. No deployment or live release identity is asserted by this increment.

Resolve the current branch head and checks from GitHub; do not mistake this file's parent anchor for the new candidate's SHA. Do not make an additional documentation-only commit solely to insert the enclosing commit's self-reference.

## Retained current native evidence

Parent integration run [35818783575](https://github.com/BoneManTGRM/NICO/actions/runs/35818783575) completed successfully. All 21 workflows on the parent head were observed completed/success; changed code requires fresh candidate checks.

- Exact-source artifact `10732314434`, ZIP SHA-256 `5ab5d0c4c6c49472b81871a250377c54af0355d12d43f0341c5c4eb895863440`. Its commit/tree and internal archive digest were verified before local source use.
- Native artifact `10732024695`, ZIP SHA-256 `dbacd9e4b9ed5e4ae18fd6d9a5659ae7e22c48bd3841d249e88d4c02a6240b6a`.
- Native image config ID `sha256:47024ad074bf2d7b8dcb6775767b6c0f335fbf3cb2a30e3590beb2d8c09f38b4`. This CI-built full-project image is not asserted to be the qualified production registry image.
- Actual owned positive and intentional negative controls completed the generated-header, compiler, isolated sanitizer replay and bounded libFuzzer pipeline. The control artifact reports `PASS_OWNED_PROJECT_INTEGRATION`, 53,846 ms overall, `synthetic_issuer=true`, `production_dispatch_exercised=false`, `bitcoin_executed=false`, `production_qualified=false`.
- Both original native receipts reconstruct their original canonical records exactly with this increment's corrected validator. Positive canonical SHA-256 `c7873d02925b3be30fc51f6c6c1cff26078ebcfc0b26eefdee2887c6d7f7a0bf`; negative canonical `9c3d03d44cf085e17a76af4f9112711d9c0581402d5d12474beaeb3aebf4b367`.
- Positive receipt SHA-256 `e3cf0771c5fe5d4c04017f448b3f2a8e463e8e22893f6450c103a83225c9a0bb`; negative receipt `bab56698c841279a9ecb9ffc3524c20ab462ee66e66de360a28f6bbc17e98311`.
- Retained owned-control PDFs are 22 pages each: English `0c44b33e9374e826f2c6e58459cb3ff799eb4ee3bafe48cf62754b4c82fefa6c`, es-MX `b127b752a3d2a247baf32dfd23eff5b7278fdc6c73cab9c5f309a11c32301bf7`. These are automated engineering drafts, not Bitcoin reports or approved client deliverables.

Earlier configuration v1/v2/v3 meanings, v4 generated-header composition, v5 fuzz composition, original CTest limitations, Spanish fixes, failed native outcomes, and the smaller worker profiles remain unchanged.

## New bounded changes and verification

### NATIVE-TIMING-1: corrected at receipt validation

The validator previously accepted individually bounded sanitizer operations whose summed duration exceeded the enclosing controller's recorded duration. This could understate aggregate execution time despite green CI. A 20,000 ms nested operation inside a 10 ms stage reproduced the defect through the existing receipt boundary.

The native-test validator now sums every recorded serial operation and compares it to the enclosing stage, using the existing fuzz convention's two-millisecond rounding allowance. Failed-stage receipts do not excuse contradictions. No native receipt or canonical/report schema changed; valid historical native records reconstruct byte-for-byte identically. Original CTest execution-time identity remains unproven, not rewritten as replay proof.

RED: 25 expected failures, six unchanged positive controls. GREEN: all 31 timing regressions. The actual retained positive/negative receipts also pass exact reconstruction. Their address/undefined nested totals were 708/691 ms inside 715/696 ms, and 694/683 ms inside 700/689 ms respectively.

### SOURCE-ARCHIVE-1: bounded generic large-population acquisition

The existing source adapter now uses one immutable-commit archive for full-project populations of at least 32 files when the whole recorded tree fits the already-declared source byte envelope. This avoids thousands of sequential per-file HTTP requests. It does not depend on the repository's name and does not activate production selection.

Commit and complete-tree metadata still establish the HTTPS identity. Original Git blob hashes and independently frozen selected SHA-256 values remain mandatory. Only selected original files are materialized. All regular archive members are verified; links/special files are never extracted. Unselected Git symlink text can be verified without creating links. Executable bits come from the frozen tree, not tar permissions. Small profiles and trees whose unselected bytes exceed the archive envelope keep the existing per-blob path.

Acquisition bounds: selected per-file 16 MiB, selected aggregate per the existing contract (at most 64 MiB), compressed archive 64 MiB, all expanded tar data including metadata/padding 128 MiB, existing lease checkpoints and deadlines. Only the exact `codeload.github.com/owner/repository/tar.gz/<40-character-SHA>` route is added to trusted pre-execution provisioning. No redirects, credentials, environment proxy inheritance, or implicit HTTP content expansion. External network remains unavailable to assessed code.

Malformed archives, digest substitutions, missing/duplicate files, traversal, unsafe types, truncated gzip, nonzero trailing data, second tar streams, excess expansion and lease loss fail before atomic promotion. No failed archive silently falls back or changes the required population. A transport hash/count receipt is retained by the adapter; existing source-method and native receipt projections are unchanged.

RED: 22 missing archive-capability cases; then four transport/scheduling regressions. GREEN: 37 archive tests plus all existing neighboring source tests. These are owned synthetic transport fixtures, not a live Bitcoin download or Bitcoin resource qualification.

### Verification scope

- 71 tests passed: new timing/archive cases and existing schedule/retention tests.
- 204 affected non-export regression cases passed; six exporter cases were explicitly excluded from that invocation.
- 175 source, launcher, capacity, generated-context, phase-boundary and fuzz-workspace neighbors passed.
- These are separate, disjoint test-file groups. Earlier combined local exporter invocations exceeded the execution timeout and are not reported as passing.
- New test files are required by the existing regression predecessor before the native integration job. Existing tests, five-minute job bounds, contents-read-only permissions and native positive/negative assertions are preserved.
- Complete new-candidate hosted CI, independent complete review, and Bitcoin qualification are not inherited from the parent.

## Acceptance state: preserve subproofs, do not promote them to whole-mission success

| Predicate | Retained evidence and remaining requirement |
|---|---|
| C0 | Pinned target and prior public discovery retained; meaningful frozen Bitcoin execution/dependency/configuration and aggregate budget still require qualification. |
| C1 | Generic original-byte acquisition and new bounded archive fixtures verified; actual full required Bitcoin population through this path not established. |
| C2 | Real owned controls demonstrate enforced full-project isolation/resources; Bitcoin workload resource qualification remains separate. |
| C3 | Existing worker authority protections preserved; synthetic control issuer is not actual production OIDC proof for the final candidate. |
| C4 | Existing durable lease/receipt/persistence/restart evidence retained; final production dispatch on the full-project profile still requires acceptance. |
| C5 | Owned configured static-analysis evidence retained; mandatory Bitcoin translation-unit/configuration coverage not established. |
| C6 | Owned build/compiler/generated-header proofs retained; Bitcoin dependencies, configurations, required targets and header population not qualified. |
| C7 | Real owned native tests, isolated sanitizer replays and bounded fuzz retained; meaningful Bitcoin test/sanitizer/fuzz execution not established. |
| C8 | Existing observation/finding/disposition boundaries unchanged; actual Bitcoin results must retain them. |
| C9 | Existing distinct source/translation-unit/header/test/fuzz populations unchanged; actual required Bitcoin populations still need reconciliation. |
| C10 | Existing score/assurance boundaries unchanged; no Bitcoin assurance is inferred from CI or declared resources. |
| C11 | 2 CPU/2 GiB/256 PID class remains bounded; real Bitcoin aggregate runtime, memory, retries and cost qualification not established. |
| C12 | Small owned C++ native evidence and focused regressions retained; complete new-candidate existing-language CI pending publication. |
| C13 | Owned bilingual report path retained; actual Bitcoin structured/PDF report not produced. |
| C14 | Parent mobile/WebKit checks passed; final candidate production bilingual/restart/mobile acceptance remains required. |
| C15 | No attestation, human review, approval, delivery authorization or historical approved artifact was altered. Actual new-edition actions remain human-controlled. |
| C16 | Parent 21 workflows passed; complete independent review was absent. New-candidate CI/review and disposition of all Important/Critical findings remain mandatory. |
| C17 | No merge or deployment performed. Exact coordinated frontend/backend/worker release identity remains a post-merge gate. |
| C18 | Actual authorized production Bitcoin assessment not executed. |
| C19 | Primary source/native artifacts and this checkpoint are retained; final production report/manifest and supported repeated retrieval remain outstanding. |

## Exact continuation

Verify the published candidate and all changed blob hashes, inspect its automatic CI and native artifacts, and obtain an actual independent review of the complete PR from the recorded base to the current head. Do not label the implementation author's own validation as independent review. Preserve each review finding until evidence-based disposition.

Continue the existing reusable dependency/configuration and qualified production-profile work, then perform the frozen Bitcoin qualification through genuinely authorized, supported execution. Successful archive fixtures or owned native controls are not substitutes. No platform denial may be bypassed, and no additional privilege or spending authority is invented.

Only merge once required implementation, pre-merge qualification, reviews and checks are satisfied. Then verify the coordinated deployed release and actual authorized production Bitcoin report, including bilingual content, approval/delivery boundaries and repeat retrieval. Do not use the final SHIPPED declaration before C0-C19 are evidenced. Never force-push, bypass checks, reclassify unknown execution as success, or ask the owner to repeat already-given permission.
