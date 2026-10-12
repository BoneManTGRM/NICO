# Isolated Cppcheck constructor AST candidate — 2026-10-12

## Change and provenance

Local NICO branch: `repair/ast-local-colon-20261012`.
Base: `611f76543b011f67f6496786aca73bb23c8c0f53` (the supplied last verified main).
The main worktree remains unchanged. This candidate is not based on or integrated
with PR1712's published head. PR1721 and the inaccessible private `aed9432` candidate
were not modified or reconstructed.

No applicable repository AGENTS.md or .agents/skills files were present; the only
AGENTS.md found was under unrelated installed Next.js dependencies.

Official public source: https://github.com/danmar/cppcheck at
`ac9db3069b9f90e81e126a090b99ad456e122cf8` (2.17.1).
Verified `lib/tokenlist.cpp` blob: `b9c3ab07f0436ada75da5f45c7f8c3f3e06a8608`.
Original SHA-256: `124d7fddb3dd90684e936544a8fdfdff61140c17a5fd173cddad4b69d07617f3`.
Patched blob: `39f33db14a8d4cd359c1f1c8ae5a4eacb534acfa`.
Patched SHA-256: `357fa22ad927318f39488aeaa7f61577f3b1eeb41cea4ca5dbbe31b5305db0cb`.
See `repair-receipt.json` and `upstream-tokenlist.patch`.

NICO's existing source-pinned, atomic patching mechanism now applies the reviewed
guard only inside `skipMethodDeclEnding`, after the original `tok2` lookup. An
exact standalone colon cancels the skip; linked `<`, `[`, `(`, `{` regions are
skipped; an unlinked opener retains the original endpoint. The placement-new
repair remains intact. Repair identity and Docker metadata advance together to
`placement-new-and-constructor-boundary-ast-v2`.

Direct source checks verified the patched file equals the patcher's output,
reversing the two exact replacements yields the original pinned bytes, and
`isFunctionHead` plus all following source are byte-identical. AST validation,
diagnostics, and early variable-ID code were not edited.

## Proposal artifact availability

Used the current Library skill and its supported resolved-reference materialization
route for `libfile_6b043f3b2b688191a47d63087bb935c3`. Resolution succeeded, but the
current transfer helper returned `library file transfer failed: download failed`.
No proposal file was materialized or hash-verified. No alternate storage route or
denial workaround was attempted. Implementation used the supplied task description
and the verified public source. Expected proposal SHA-256 remains
`e58cad951ab2746f49f50ba57cd613a5c4bb2982613c8ec9d859835356b78e86`.

## Executed tests

Environment: Debian g++ 14.2.0-19, Python 3.12.14, pytest 9.1.1. Ordinary local
source builds used `-O0`, retaining AST validation, with two compile jobs.
Exact native build/run commands are in `tests/native/README.md`.

| Check | Result | Evidence |
| --- | --- | --- |
| `pytest -q tests/test_cpp_constructor_ast_boundary.py tests/test_cpp_placement_tool_repair.py tests/test_cppcheck_execution.py tests/test_cpp_integration_workflow_schedule.py` | 48 passed, 3.35 s | `python-tests.txt` |
| Patched upstream `TestTokenizer TestVarID TestTokenList` | 558 tests, 0 failures, 6 existing TODOs | `upstream-tests.txt` |
| Owned initializer/qualifier/variable-ID fixture | 9 tests, 0 failures, 0 TODOs | `owned-tests.txt` |
| Same owned fixture with tokenlist coverage instrumentation | 9 tests, 0 failures | `coverage-excerpts.txt` plus local coverage log |
| Exact pinned-source/two-replacement verification | Passed | hashes above, `upstream-tokenlist.patch` |
| `git diff --check` | Passed | local verification |

Boundary shim tests distinguish `:` from `::`, skip linked delimiter regions,
retain endpoints on each unlinked opener, cover both helper entry forms, handle
null/immediate endpoints, and stop after links crossing the candidate endpoint.
These are isolated helper tests, not proof of complete tokenization.

Owned native tests assert reciprocal AST parent/child links for initializer
arguments across parenthesized, braced, base, delegating, and multiple initializers,
nested constraints, and `noexcept`. They check `noexcept`/trailing `decltype` call
ASTs and consistent nonzero parameter variable IDs through the normal tokenizer.
Some cases intentionally exercise parser forms, not compiler-validated programs.

Coverage from the final owned suite shows the direct helper call at patched line
1611 executed 307 times and the declaration helper call at line 1824 executed
9 times. Both returned non-null at least once. This establishes call-site
execution, not exhaustive branch or real-header coverage. An initial custom-runner
class filter selected zero tests; it was corrected, and only the final nonzero
runs are counted above.

## Integration limits and holds

These results are source/unit regression evidence, not full native qualification.
The published `rpc/client.cpp` failure (`__i does not have a parent`, GCC14.2
`ranges:1935:29`, 41.1 seconds, exit 0) remains unreproduced; its exact real token
and header identity are not established. The separate private `format:299:74`,
212-second failure is not evidence for this candidate.

Never run here: old/current 12-case native binary comparison, any Bitcoin binary
comparison, frozen Bitcoin modifications, full static/header qualification,
Docker/toolchain image build, production-impact inspection, previously blocked
operation, workflow start/rerun, push, merge, or deployment. No old baseline
container, paid service, new capacity, TinyFish, or database pilot was used.
No compiler #error or sanitizer evidence was removed.

The explicit contract workflow test list now includes the new Python boundary
tests; the workflow has not run. Native tests remain explicit local tests.
Before any publication, the parent must reconcile ownership with the earlier task.
Later integration must reconcile PR1712 and preserved private changes, obtain the
full proposal if needed, and complete authorized full static execution/header
qualification before gated merge. Database pilot remains HOLD.

Independent review and its disposition are recorded in `review.md`.
