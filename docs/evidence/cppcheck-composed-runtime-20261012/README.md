# Composed analyzer runtime validation and local correction

Published candidate tested: `fc9a0a75ac2cdd614304d7483eb8cbaf3b161b01`.
Pinned upstream: `ac9db3069b9f90e81e126a090b99ad456e122cf8` (Cppcheck 2.17.1).
This follow-up is local only; the published branch was not changed.

## Why a new build was necessary

All nine composed source files differ from the source used for the earlier 558
upstream and 9 owned native tests. `source-comparison.json` records both hashes.
The grammar and observer layers change tokenization, AST construction, preprocessing,
and Cppcheck integration. Earlier runtime evidence therefore could not establish
compatibility of this composed source. This was an ordinary single-candidate test
build, not the prohibited old/current 12-case comparison.

Created a fresh local upstream worktree and applied the published AST → grammar →
observer scripts. All nine resulting source hashes matched the published source
composition receipts before compilation. Used the normal upstream Makefile,
g++ Debian 14.2.0-19, GNU Make 4.4.1, `CXXFLAGS=-O0`, and two compile jobs, with
180-second build/test bounds. No source or binary from the old environment was used.

## Published-candidate result and defect

The composed build succeeded in **54.539 seconds**. Its 9 owned native tests passed.
The expanded upstream run completed **1,232 tests, 33 TODOs, 1 failure** in
16.296 seconds. The exact failure was `TestTokenizer::astfunction`, upstream
`test/testtokenize.cpp:6747`:

```cpp
int* g(void* (f)(void*), void* u);
```

Expected AST text: `voidu*`. Observed: `f( voidvoidu*,`.
The published grammar patch treated a parenthesized function parameter declarator
as a pointer-type conversion and created a call AST. This failure is separate
from the still-unreproduced GCC `ranges:1935` case.

## Local correction

Only the grammar patch's `compileTerm` replacement changes parser behavior.
After `findCppTypeInitPar` has recognized a builtin type plus pointer/reference
tokens, `( name ) (` retains the original declaration stepping. Other forms still
parse argument expressions and retain the existing AST depth guard. Shared
`isFunctionHead`, constructor-boundary logic, diagnostic handling, and AST
validation are unchanged.

Grammar identity advances to `physical-header-grammar-v3`; Docker metadata now
matches it. The prior label was v1 while the published script identified v2.
Owned native tests add two declarator forms and three pointer-conversion argument
forms. The latter are post-template-substitution parser forms, not a claim of
compiler acceptance for that raw spelling. Instructions now apply all three
patch stages, fail on errors, and retain bounded commands.

## Fixed-candidate results

| Check | Result |
| --- | --- |
| Incremental build of the changed tokenlist translation unit | Passed, 1.960 s |
| Previously failing `TestTokenizer::astfunction` | Passed |
| Eight selected upstream classes | 1,232 tests, 33 TODOs, 0 failures; 16.297 s |
| Expanded owned native runner | 11 tests, 0 TODOs, 0 failures |
| Affected offline/project tests | 144 passed, 1 existing Python escape warning; pytest 5.90 s |
| Fresh AST → grammar-v3 → observer derivation versus tested source | All 9 files byte-identical |

Upstream classes: `TestTokenizer`, `TestVarID`, `TestTokenList`, `TestToken`,
`TestPreprocessor`, `TestCppcheck`, `TestSimplifyTemplate`, `TestSimplifyTypedef`.
Their source dependencies justify expanding beyond the earlier three classes.
Complete outputs and command/resource records are retained alongside this report;
original raw logs remain in `/workspace/ast-composed-runtime-evidence`.
Repository text copies normalize trailing whitespace and newlines. Binary hashes identify
the tested runners; no historical binary was executed for comparison.

The corrected tokenlist blob is `7de267cbdd1aef164c6396d621ee453f252d0a07`.
Final source hashes and script-bound receipts are in `fixed-final-*.json`.
Separate independent review found no blocking findings; see `review.md`.

## Resource use and remaining acceptance gaps

Used existing workspace resources only. Initial build reported 102.121 user CPU
seconds, 10.311 system CPU seconds, and maximum child RSS 387,784 KiB (about
379 MiB; not aggregate concurrent-process memory). Two compile jobs were the
maximum. New source/build directory measured 94 MiB; retained local evidence and
binaries measured 42 MiB before packaging. No purchases, capacity increases,
destructive cleanup, containers, remote jobs, workflow reruns, or API reads.

Wall times are recorded per command. Early grouped-shell child CPU/RSS accounting
can include inherited child counters, so those rows should not be blindly summed.
The recording helper was corrected to report CPU deltas and inherited RSS for
subsequent commands. The native build and its complete outputs remain preserved.

These are local correctness results for the corrected composed parser, not full
qualification. Still outstanding: production Docker build and release flags
(`MATCHCOMPILER=yes`, `-O2 -DNDEBUG`), exact retained GCC-header/token reproduction,
full static/header evidence and project qualification, Bitcoin execution, and
remote CI status. No Bitcoin or prohibited native comparison was run. Compiler
and sanitizer evidence was not removed. Qualification flags remain false.

No push, PR creation, merge, deployment, or previously denied API retry occurred.
The published `fc9a0a75` candidate still contains the newly identified defect;
this separately reviewed local correction requires a later publication decision.
