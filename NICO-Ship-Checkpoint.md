# PR1641 continuation — source-pinned placement initializer repair

Continue PR #1641 / `feat/cpp-full-project-capacity`. Candidate parent is `cf07a31d2c67470b605d618c3c324b42b7a95704`, tree `3550616e8dffdbf0cba591190d472bdd76efe816`; main/base last read `faaa10b037eb58e4175561b96dadf0d929764df4`. Recheck live refs before non-force publication and preserve concurrent descendants. The local detached source-export fixture has no remote and MUST NOT be pushed. Record publication identity in the PR, not a self-hash commit. Original and stronger C0-C19 requirements remain binding.


## Security audit exact public-source disposition

Security Audit Evidence run36055047175 completed every scanner but the final fail-closed gate blocked on one new Gitleaks observation. Artifact10832023290 (SHA256 `19122e8002bc33050a4eca98b04cd056eeeeeb5d4a7f2e59664982af6bc41f30`) identifies the exact source as `docs/evidence/pr1641-placement-ast-20260924/verification.json:45` in commit `923d5b92254f73aa297bb1f00c9929236125853f`. The redacted match is the recorded public upstream Cppcheck `tokenlist.cpp` Git blob identity; the same verification record separately binds upstream commit/source hashes. It is not a credential.

The security gate now dispositions only that complete immutable locator (commit, path, rule, redacted match, fingerprint, line and columns) as `approved_public_source_hash`. No rule class, path prefix, generic hash, test directory or secret value is broadly allowed; changed commit/path/line/match/value observations still block. Recorded focused RED failed before the correction; focused GREEN passes. Full `test_security_audit_gate.py`:29 passed. A wider local source-export security invocation had75 passes and2 setup failures solely because that bounded source export omits unrelated `apps/web/package.json` and `pyproject.toml`; those two are not credited as candidate passes. Hosted Security Audit Evidence remains required on the published candidate.

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

EXACT NEXT ACTION: publish the exact public-source security disposition as a non-force descendant, verify the hosted security gate and patched owned C++ control, then let the frozen Bitcoin qualification run. Preserve any new first failure without dropping contexts, diagnostics, depth or resource enforcement. Continue durable normal-intake/canonical/report integration and permitted runtime work, then obtain independent review and final gates before merge/deploy and actual English/es-MX production Bitcoin acceptance.

## Immutable continuity

Full predecessor ledger: `cf07a31d2c67470b605d618c3c324b42b7a95704:NICO-Ship-Checkpoint.md`. Its516/e372/50e/8f7/e118/95f/533d/3652/2195/a561/cbecc chain preserves original C0-C19, PR1627, native successes/failures, approvals and history. Historical Bitcoin revision0e9018e8b65611b0769545e177110e4b7fc51244/runcomprun_7cc47a5a81695fa452354479ea23b422 remains unchanged. This is the sole active ledger.
