# PR1712 detached integration validation

Exact base: `e16ae785fffd0f6ba12ceeeb006dc4e57ffce345`.
Applied the previously reviewed `nico-ast-pr1712.patch` to a fresh detached
worktree. Original main-based candidate `deb20552` and its Library handoff are
unchanged. No private chain was applied.

## Fresh integration finding and repair

The first 67 affected tests passed, but a real pinned-source composition check
failed: the AST repair emits `39f33db14a8d4cd359c1f1c8ae5a4eacb534acfa`, while
PR1712's following grammar patcher requires the old placement-only output
`f6e28dfb9bb4358d93fa6ab5ac227346164880a3`. Its fail-closed rejection was
`upstream_source_mismatch`, before grammar writes. The earlier applicability and
adaptation reviews established textual preservation, not toolchain composition.

Integration repair changes only the grammar patcher's expected tokenlist input
hash and its explanatory comment. Grammar replacement algorithms are unchanged.
The strict pin was updated to the exact verified AST output, not relaxed.

Added `tests/test_cpp_tool_patch_composition.py` and its workflow test-list entry.
The source tests read immutable objects at upstream commit
`ac9db3069b9f90e81e126a090b99ad456e122cf8` from a local checkout, without fetching.
They execute AST → grammar → observer against copied source, check receipts and
preserved AST guards/shared `isFunctionHead`, and reject placement-only input
before any grammar mutation. The observer touches six disjoint files.

The resulting composed `lib/tokenlist.cpp` blob is
`00027133f6ca35e6a2ea38210c34abcea8575466`. Receipts and all nine composed source
SHA-256 values are retained here. All qualification flags remain false.

## Fresh executed checks

Environment: the existing Python 3.12.14 / pytest 9.1.1 / g++ 14.2.0 workspace.
No installs, containers, network tests, paid services, or workflow runs.

```sh
NICO_CPPCHECK_SOURCE=/workspace/cppcheck-ast-source /workspace/nico-venv/bin/python -m pytest -q tests/test_cpp_constructor_ast_boundary.py tests/test_cpp_placement_tool_repair.py tests/test_cpp_header_grammar_repair.py tests/test_cpp_tool_patch_composition.py tests/test_cppcheck_execution.py tests/test_cpp_integration_workflow_schedule.py tests/test_cpp_worker_image_handoff.py tests/test_cpp_header_transport.py tests/test_cpp_physical_header_inputs.py tests/test_cpp_header_evidence.py tests/test_cpp_header_incomplete_fallback.py
```

Result: **144 passed in 5.72 seconds**, with no skips. The focused composition
run separately passed all three tests. The first composition-test authoring run
had a wrong receipt key (`sources` instead of `members`), corrected before the
passing runs; its log is preserved with the external raw evidence.

Without `NICO_CPPCHECK_SOURCE`, the two source-dependent tests explicitly skip;
the constant-pin assertion alone does not prove composition. The current workflow
does not provision this variable in contract-regressions, so this stronger check
is local evidence only. No CI execution is claimed.

## Evidence transfer and limits

The AST patcher and native fixtures are unchanged from `deb20552`. Its 558 selected
upstream passes (6 TODOs), 9 owned native passes, and both-helper call coverage
remain valid evidence for that original pinned source plus AST repair. They were
not rerun. They do not become native evidence for the newly composed PR1712
grammar/observer source, which has additional source changes.

Fresh checks were necessary for the published patch sequence, exact hash handoff,
Docker/workflow metadata, header receipt handling, and evidence fallback behavior.
These now pass at the source/project-test level. No fully composed analyzer was
compiled or run; no real GCC retained case, Bitcoin run, native binary comparison,
full static/header qualification, or production-impact audit was performed.

Earlier manifests in `cppcheck-constructor-ast-20261012` describe the historical
main-based candidate. The PR adaptation manifest describes the earlier textual
projection. Use this directory's `integration-code-sha256.json` for the changed
integration files; do not treat historical workflow hashes as current.

Separate targeted independent review found no blocking findings; see `review.md`.
Old-writer acknowledgment is still absent. Publication, merge, deployment, and
workflow execution remain on HOLD.
