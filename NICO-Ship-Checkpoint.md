# PR1641 continuation — static validation scaling repair

Continue PR #1641 / `feat/cpp-full-project-capacity`. Candidate parent is `42abcc8c5c151e73ac5765b87b0646ce95fa8bd1`, tree `479a92fc217fed491695044afa655b4914213c9d`; main/base last read `faaa10b037eb58e4175561b96dadf0d929764df4`. Recheck live refs before non-force publication and preserve concurrent descendants. The local detached source-export fixture has no remote and MUST NOT be pushed. Record publication identity in the PR, not a self-hash commit. Original and stronger C0-C19 requirements remain binding.


## Security audit exact public-source disposition

Security Audit Evidence run36055047175 completed every scanner but the final fail-closed gate blocked on one new Gitleaks observation. Artifact10832023290 (SHA256 `19122e8002bc33050a4eca98b04cd056eeeeeb5d4a7f2e59664982af6bc41f30`) identifies the exact source as `docs/evidence/pr1641-placement-ast-20260924/verification.json:45` in commit `923d5b92254f73aa297bb1f00c9929236125853f`. The redacted match is the recorded public upstream Cppcheck `tokenlist.cpp` Git blob identity; the same verification record separately binds upstream commit/source hashes. It is not a credential.

The security gate now dispositions only that complete immutable locator (commit, path, rule, redacted match, fingerprint, line and columns) as `approved_public_source_hash`. No rule class, path prefix, generic hash, test directory or secret value is broadly allowed; changed commit/path/line/match/value observations still block. Recorded focused RED failed before the correction; focused GREEN passes. Full `test_security_audit_gate.py`:29 passed. A wider local source-export security invocation had75 passes and2 setup failures solely because that bounded source export omits unrelated `apps/web/package.json` and `pyproject.toml`; those two are not credited as candidate passes. Hosted Security Audit Evidence remains required on the published candidate.


## Bitcoin static validation scaling defect and repair

Run36056863546/job107832568836/artifact10835331499 (ZIP SHA256 `6fc3e5f37e0b66c783b7aac0c3ccefb434bdf558c5dc1dc31a0dbe901a9b8014`) proves the patched full-project analyzer reached frozen Bitcoin after owned controls. Build/tests/compiler evidence remained successful, and native static execution itself returned475 records in356,499ms. The stage nevertheless reported `worker_project_static_stage_deadline` at863,639ms. The retained stage operations show environment capture2,532ms and native static execution356,835ms; the unexplained remainder occurred in controller validation, not target execution or resource exhaustion.

Profiling the exact retained 4,665,074-byte static artifact identified two repeated controller computations: the same native-evidence SHA256 was recomputed for every finding/modeled input, and every `missingIncludeSystem` diagnostic rebuilt/sorted the same context dependency population. With31,873 findings and138,106 modeled inputs this multiplied work without adding evidence. The repair computes the immutable native digest once and passes the already-validated per-context dependency map into modeled-header classification. No evidence field, finding, limitation, context, analyzer invocation, deadline, resource limit, hash contract, model policy or completion rule changes.

Exact-artifact replay after repair validates in20.675 seconds on the local Python3.13 environment, versus the hosted stage's hundreds of seconds of controller validation. Native execution remains unchanged. Focused environment/static/stage suite:122 passed. A wider C++ invocation was interrupted by the local command window after partial progress and is not credited; hosted contract/native checks remain authoritative. This repair invalidates only controller validation timing, not the retained native bytes.

## Reproduced earliest remaining analyzer defect

Retained run36024277039/job107720070151/artifact10819979024 contains the source-bound `internalError` / `AST cyclic dependency` at first-party `src/coins.cpp:340`. The raw compact static artifact is3,878,970 bytes, SHA256 `25a3f643d2a7172eeefc592500ba509f904795ebd2cc33b9733dac12a86f558a`. Preserve it unchanged. The newer Boost metadata repair and its pending native qualification are not reset.

A seven-line owned program using destruction followed by `::new (&resource) Resource{};` reproduces the same internal error with the hash-verified Cppcheck2.17.1 executable. GCC14.2.0 accepts that exact program with `-std=c++20 -fsyntax-only`, exit0. Cppcheck exits0 but emits the internal error and a critical checkersReport; the corrected native-output validator correctly refuses completion. Native RED is in the evidence index, not inferred from a green process exit.

The pinned upstream parser sends the braced initializer after a placement argument list through `compileTerm`, which consumes the outer scope node. Attaching the new-expression to that scope then creates a cycle. The candidate changes only initializer dispatch in the trusted analyzer source: recognize the preceding `new (...)` and retain the existing new-expression initializer path. It does not rewrite assessed source, catch/suppress the internal error, skip a context, or reduce checks.

## Implemented candidate and exact tool identity

`scripts/repair_cppcheck_placement_ast.py` accepts only upstream commit `ac9db3069b9f90e81e126a090b99ad456e122cf8`'s exact `lib/tokenlist.cpp` Git blob `b9c3ab07f0436ada75da5f45c7f8c3f3e06a8608`. Source size/no-follow/type and unique-anchor checks precede an atomic replacement. Unknown, changed, ambiguous or already-patched input is rejected. The build retains original/patched source hashes, script hash and repair ID `placement-new-initializer-ast-v1`; original license notices remain. Base tool version is2.17.1, with the distinct repair ID and exact resulting image identity, not a claim of an unmodified upstream build.

Both existing full-project image build paths copy the same script. The Docker recipe applies it before compiling the tool, records `/opt/nico-cppcheck-repair.json` and the image repair label. The existing bounded analyzer export retains that receipt. No assessed repository code enters tool provisioning. Existing GCC/LLVM/Cppcheck source pins, resource limits, timeouts, storage caps, job order, concurrency and permissions remain unchanged.

The existing owned compiler-environment control now exercises the placement-lifecycle construct in both original repeated compilation contexts. It still has four contexts, a real generated source, generated/unused headers, clean and known-diagnostic variants, and a link-negative case. Native return values remain1+2+42=45. All existing controls still precede Bitcoin. The repaired analyzer has NOT yet been built or executed in this local session; the actual hosted owned result must establish native GREEN before Bitcoin qualification can run.

## Verified local evidence and limits

Eight new boundary/wiring tests were recorded RED against the parent, then all8 passed after implementation. The affected environment/static/stage/generated/configuration group passes226 tests. The disjoint tool-build/dependency/schedule group passes66. Combined unique JUnit membership is292 with zero failures/errors/skips; the8 are included, not additive. Full workflow collection is949 cases in36 files; no complete949-case execution is claimed here. All14 workflow shell blocks, changed Python ASTs, three existing embedded programs and diff whitespace pass. Local Python3.13 differs from hosted Python3.11. Initial unchanged baseline45-case check had one existing warning.

Exact commands, native old-tool/GCC outputs, source hashes and test membership are recorded under `docs/evidence/pr1641-placement-ast-20260924/`. These are local verification records, not another ledger or a production report. Source export artifact10831008944/ZIP SHA256 `1a503ca66ad4a88850348d63ebd9e4e958c75787c0411ad5c5354a9df8d5e106` and its inner checksum/tree were verified. Its CI merge `dc36e2d5d6ad45cc0dec24983a048c55d2f50706` is not a production merge.

## Preserved scope and whole-row acceptance

Frozen Bitcoin remains `bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`, tree `186194c9de7f613d2d323db41cb8ce6bf1e3e549`. Preserve all475 contexts, Linux Debug wallet/tests/IPC/embedded data, generated/header evidence and377 native tests. The required additional functional/integration/sanitizer/fuzz scope remains unfinished. No new privilege, spending, duplicate workflow dispatch, production activation or human approval occurs here.

| Predicate | Status | Retained scope / remaining proof |
| --- | --- | --- |
| C0 | UNPROVEN | Current authority/refs recovered; full runtime scope and aggregate production qualification remain. |
| C1 | PASS | Historical complete immutable inventory; production revalidation is C18. |
| C2 | UNPROVEN | Prior isolated boundaries retained; complete workload/production enforcement remain. |
| C3 | UNPROVEN | Full production identity and receipt authority binding remain. |
| C4 | FAIL | Configure-first full-project evidence is not connected through normal durable production completion. |
| C5 | UNPROVEN | Native parser RED reproduced; candidate patched-tool and all475-context completion pending. |
| C6 | PASS | Historical baseline/generated/compiler/header proof retained, not new production proof. |
| C7 | UNPROVEN |377 baseline tests historically pass; declared integration/sanitizer/fuzz scope remains. |
| C8 | UNPROVEN | Actual native-to-canonical/report identity reconciliation remains. |
| C9 | UNPROVEN | Required populations preserved; complete analyzer/runtime/report reconciliation remains. |
| C10 | UNPROVEN | Scoring unchanged; actual final report projections remain. |
| C11 | UNPROVEN | Correct complete combined workload capacity remains unqualified. |
| C12 | UNPROVEN |292 distinct affected local tests pass; patched native owned controls pending. |
| C13 | UNPROVEN | Actual complete-scope production Bitcoin report absent. |
| C14 | UNPROVEN | Final bilingual/mobile/progress/recovery acceptance absent. |
| C15 | UNPROVEN | Approval/history untouched; final eligible exact-edition acceptance remains. |
| C16 | FAIL | Complete native qualification, final checks and independent review remain. |
| C17 | FAIL | PR unmerged; no new production serving release. |
| C18 | FAIL | No normal production Bitcoin run exercising completed capability. |
| C19 | UNPROVEN | Final bilingual artifacts/hashes/repeated retrieval absent. |

Source publication is available; a no-op non-force ref check succeeded. Prior Codex review allowance exhaustion remains separate: no unchanged retry, extra credits/account, waiver or author-review substitution. Earlier rejected Bitcoin discovery must not be evaded; this work is the permitted generic tool-parser repair. No merge, deployment, professional disposition or delivery authorization is claimed.

EXACT NEXT ACTION: verify this published release-owned normal-intake selector, current worker image publication/retrieval, and canonical reconstruction in hosted checks while the frozen Bitcoin qualification runs. Then complete sanitizer/fuzz runtime scope, independent review/final gates, merge/deploy, configure exact qualified release/image settings, and run the actual bilingual production Bitcoin assessment.

## Immutable continuity

Full predecessor ledger: `cf07a31d2c67470b605d618c3c324b42b7a95704:NICO-Ship-Checkpoint.md`. Its516/e372/50e/8f7/e118/95f/533d/3652/2195/a561/cbecc chain preserves original C0-C19, PR1627, native successes/failures, approvals and history. Historical Bitcoin revision0e9018e8b65611b0769545e177110e4b7fc51244/runcomprun_7cc47a5a81695fa452354479ea23b422 remains unchanged. This is the sole active ledger.


## Generic Clang fallback for Cppcheck-incomplete contexts

Retained Bitcoin artifact10835331499 and reconstructed proof establish that the primary Cppcheck pass attempted all475 required contexts but completed419. The remaining56 are analyzer-specific incompleteness:47 syntax errors,3 unknown-macro failures,1 placement-new internal error,1 additional AST initializer error and4 incomplete native executions. These remain disclosed limitations.

A second substantive analyzer path is implemented generically only for contexts the validated Cppcheck proof actually attempted but did not complete. It binds the primary request/evidence/compiler identities, preserves the frozen translation-unit configuration, verifies immutable inputs, and invokes pinned Clang17 static analysis inside the same private static sandbox. Fallback failure never earns completion; all Cppcheck limitations remain disclosed.

Fallback limits are180 seconds wall /45 seconds per context /4 workers /32MiB evidence, with exact raw plist SHA256 retained. No Bitcoin-name special case, context removal, analyzer-depth reduction, deadline increase or compiler-success substitution is introduced.

Local verification:7 fallback-specific and228 affected tests pass. The retained Bitcoin proof selects exactly56/475 contexts and serializes a557,374-byte request. Hosted native fallback qualification remains mandatory.


## Freeze-after-configuration production contract

The configuration probe now accepts a strict `nico.cpp-baseline-execution.v2` policy that does not require an engineering-precomputed compilation-database digest. Source revision, target population and project options remain fixed first. The isolated CMake configuration then produces the actual compile database; NICO hashes and freezes that exact population before any build, native test, generated-input capture, compiler evidence or static-analysis stage executes. The post-build database must still match the frozen digest exactly.

The historical v1 contract remains unchanged and continues to require its supplied database SHA. v2 accepts only the explicit `after_configuration_before_build` freeze point and rejects a caller-supplied database hash, preventing a public or stale caller from mixing the two authority models. This is generic configure-first plumbing for normal CMake repositories; it contains no Bitcoin repository-name rule.

Local affected verification:84 tests passed with zero failures/errors/skips. Production selection and durable worker execution remain gated on native qualification and are not activated by this contract alone.


## Complete-tree source freeze for configure-first production

The production source adapter now has a versioned internal `cpp-configure-first-v2` contract. It binds the exact commit and expected Git tree before acquisition, permits no caller-supplied SHA256 target map, and uses the existing bounded codeload archive verifier to materialize every regular `100644`/`100755` blob. Each member is checked against the Git tree object identity while streaming; its SHA256 is derived and frozen before any CMake command may execute. Symlinks and gitlinks remain explicit exclusions; a C/C++ source/header symlink fails closed. LFS pointers remain unsupported rather than silently fetched.

The new profile uses the existing 4 CPU /12 GiB /9 GiB scratch qualification envelope and the strict baseline-execution-v2 freeze point. It is internal only: public intake still cannot choose a profile, image, source population, build option or budget. Production execution and receipt projection are not activated by this commit. Legacy worker contracts and pre-frozen target acquisition remain unchanged.

Local verification:72 focused source/capacity/contract tests pass. Broader worker/receipt/launch/baseline/workflow regression:195 passed after adding temporary local Git metadata to the source-export fixture; the local `.git` directory is not published.


## Lease-bound production artifact transport

The configure-first production worker now has a bounded authenticated artifact operation for large native evidence that cannot fit truthfully inside the final8MiB receipt. Only five known C++ evidence kinds are accepted: generated-context, compiler-evidence, static-environment, primary-static-evidence and Clang-fallback evidence. Upload authority is bound to the active durable job lease, exact worker identity, tenant/run/repository/revision and the internal `cpp-configure-first-v2` profile.

Each artifact is gzip-compressed by the worker, capped at8MiB compressed /64MiB raw, transferred in a separately enforced12MiB JSON envelope (the measured base64 transport overhead for the retained Bitcoin artifacts), decompressed with a bounded read on the backend, and verified by raw/gzip SHA256 and exact byte counts before insertion into NICO's existing private PostgreSQL immutable artifact store. The stored scanner binding uses the exact child scan and a key-specific `cppcheck:<artifact-key>` identity. Lost-response retries are idempotent only for identical bytes; a changed artifact cannot replace an existing immutable slot. No artifact operation is available to other worker profiles.

The final receipt remains independently bounded to8MiB and will reference these durable artifacts rather than duplicating tens of MiB of native bytes. This commit adds transport/storage only; it does not itself activate configure-first execution or claim production qualification.

Verification:72 focused worker/jobs/API tests pass. Broader source/capacity/jobs/consumer/API/receipt/launch/configure-first/baseline/workflow regression:267 passed, zero failures/errors/skips.


## Durable configure-first execution and compact receipt

The internal `cpp-configure-first-v2` contract is now executed through the existing authenticated durable worker rather than a parallel manual path. After exact-tree acquisition derives and freezes the complete SHA256 source population, the worker invokes the existing isolated configure/build/test/generated-context/compiler/static pipeline with the contract's release-owned capability set. Large generated/compiler/environment/Cppcheck/Clang evidence is uploaded through the lease-bound artifact operation already retained in PostgreSQL; the probe receives compatibility references only after those durable uploads succeed.

The final worker receipt advances to `nico.worker-native-receipt.v7`. It carries the derived source population, exact configuration identity, compact count+SHA256 summaries for test/compiler/static populations, resource/timing truth and the immutable PostgreSQL artifact references. It does not duplicate the large native payloads. Backend validation binds the receipt's source population to the complete-tree provisioning receipt and requires its artifact map to equal the artifacts retained under the same active job lease.

This commit deliberately does NOT mark canonical scanner completion. Even when native configure/build/tests/compiler/static execution is complete, the scanner record remains `partial` with `canonical_findings_projected=false` until the backend reconstructs canonical findings from the retained static artifacts. The native finding count is retained, but an empty projected finding list cannot be mistaken for zero findings. This preserves the existing truth-stress requirement while connecting the durable execution path.

The configure-first worker can use up to2400 seconds of the existing2420-second job wall budget; all other profiles retain the prior300-second consumer ceiling. Public intake still cannot choose this profile.


## Backend canonical reconstruction from retained native bytes

Configure-first completion no longer trusts the worker's compact summary as canonical finding truth. The worker now also retains the exact frozen compile database as `project-compilation-database`. During final receipt publication, the backend reads every referenced PostgreSQL artifact under the exact tenant/run/repository/revision/key binding and verifies compressed/raw hashes and byte counts.

Without executing assessed code, the backend rebuilds the compilation contexts from the retained database, validates the generated snapshot, reconstructs the compiler request and validates compiler evidence, reconstructs and validates the compiler environment, rebuilds the static request and validates primary Cppcheck evidence, and when present rebuilds/validates the Clang fallback before merging coverage. Every compact count/SHA256 in the v7 receipt must equal the independently reconstructed population.

Only after those checks pass does the scanner row become completed. The full canonical finding population is bound to the exact commit/configuration and evidence artifact, given stable observation IDs, and stored in the scanner record; retained limitations and exact context coverage remain attached. An incomplete native run remains incomplete. This closes the intentional `canonical_findings_projected=false` gate from the previous commit without replaying target code.


## Protected worker workflow budget alignment

The dedicated protected-main `Assessment Worker` workflow still had a5-minute GitHub job timeout even though the internal configure-first job contract is bounded to2420 seconds and target execution to2400 seconds. That outer CI ceiling would terminate a legitimate large-repository assessment before the durable lease/job budget could decide its outcome.

The workflow timeout is now45 minutes (2700 seconds), leaving bounded setup/finalization headroom around the existing2420-second durable job wall limit. The workflow still accepts only `job_id`, keeps `contents: read` plus `id-token: write`, has no public profile/image/budget input, and does not weaken any worker-side deadline, lease, retry or container resource limit.


## PR1641 worker-image release binding

The worker-image publication and independent retrieval controllers were still hard-bound to the historical PR1627 branch `feat/large-repository-cpp-comprehensive`. That prevented PR1641 from using the guarded publication path for its current exact image.

The branch identity is now `feat/cpp-full-project-capacity` consistently in the boundary workflow, separate retrieval workflow and release-controller identity checks. The publication gate remains push-only, first-attempt only, exact repository/workflow/source bound, package-write only in the publish job, with a retained pre-push reservation and independent retrieval. Publication/retrieval still leave `production_qualified=false`.

This commit intentionally carries the existing `[publish-worker-image]` trigger so the current branch can exercise that guarded path. It does not bypass Bitcoin qualification, merge gates or production activation.


## Release-owned generic C/C++ selection from normal intake

Normal snapshot intake now evaluates the attached exact repository evidence for a generic configure-first candidate. Selection requires an exact GitHub commit/tree, anonymous-public access, complete tree inventory, a root `CMakeLists.txt`, and at least one C/C++ source path. Repository names are never consulted.

The profile remains release-owned and fail-closed. It is selected only when deployment settings explicitly enable configure-first execution, the existing worker dispatch gate is enabled, an exact worker image config digest is present, and `NICO_CPP_CONFIGURE_FIRST_QUALIFIED_RELEASE` equals the serving backend release SHA. Public request fields still cannot provide a contract, image, budget, tool version, project option or enablement value.

The normal snapshot handler passes the internally constructed `cpp-configure-first-v2` contract through the existing additive C++ child path, preserving all ordinary required scanners and parent/child composition. If any source/capability/release predicate is absent, intake uses the unchanged ordinary scanner path.

The public GitHub source adapter now accepts both canonical `owner/repo` locators and `https://github.com/owner/repo` identities, normalizing only for acquisition while retaining the original repository identity in job/evidence bindings.
