# Complete collection and failed target tests are separate results

The owner explicitly requested implementing the reviewed separation after the complete
Bitcoin run finished. This change intentionally adds an opt-in collection decision;
it does not rewrite the historical qualification criteria or any target test result.

## Contract

The native qualification command retains its original status, error, complete flag,
JUnit populations and diagnostic bytes. An explicit `--accept-completed-collection`
selects receipt v2 and writes a separate `collection-acceptance.json` only after all
native evidence is reconstructed. A successful command under this policy means the
planned collection finished; `target_tests_passed` states the independent target result.
The full native workflow explicitly selects this policy and records its NICO revision.
Existing callers retain receipt v1 and their original exit semantics.

The new decision requires the frozen baseline database, unfiltered native baseline
commands, complete baseline membership, both sanitizer populations, all selected
functional tests, every compiler/static context, both fuzz replays and the requested
campaign executions. Completed sanitizer Failed results are admitted only with an
untruncated nonempty diagnostic, known zero OOM counters, available scratch, and
successful independent operations. Missing, skipped, timed-out, crashed or invalid
results do not become accepted collection. There is no target/test-name allowlist.

All source, plan, option, image, producer and artifact identities are bound. Compiler,
static and runtime native artifacts are revalidated, including raw result bytes and
original receipt agreement. Only the frozen-database baseline v1 contract is admitted
by this first collection policy; freeze-at-config v2 remains outside its scope.

`full_project_qualified` and `production_qualified` remain false. Existing image
export/promotion accepts neither this collection decision nor the v2 receipt as a
clean full-project qualification. Static observations remain observations, and
unverified analyzer header coverage remains unverified. No target source, toolchain,
resource ceiling, workload population or deadline changes.

## Retained native evidence

Run 36250553285 on candidate bda72c7 completed on September 26, 2026 at 20:09 UTC.
Artifact 10913709745 is 20,848,472 bytes with SHA256
`80df3cb7989587655cb5ffbfb470b37d851c6dd2f108f227e6695a464c3749ca`.
The archive was downloaded and verified before this change.

Baseline 377/377, compiler/static contexts 475/475, functional 6/6 and ASan 377/377
passed. UBSan executed 377 with net_tests failed at streams.cpp:99:24; 376 passed.
The two-worker fuzz build completed in 948.902 seconds, both required replays passed,
and the connect_block campaign completed 256 executions with coverage signal 6663.
The original run remains FAILURE and runtime.complete remains false. This is a
retained target-source finding, not proof of exploitability or a clean target.

A data-only application of the new policy uses a separately labelled prospective v2
copy and externally supplied GitHub provenance. It does not modify the historical v1
receipt, authenticate missing historical fields, or constitute new native execution.
The original runtime summary remains identical. Exact current-candidate hosted
verification is still required after publication.

## PDF acceptance remains separate

PR1645 remains c6f9f4c. Read-only source review established that the final renderer
context was temporary and no durable exact replay capsule exists for the failed
revision67 attempt. Saved Markdown/HTML are sibling outputs, not the structured
ReportLab input, and may come from an earlier report stage. A diagnostic export of
those documents would not satisfy actual failed-input replay. No endpoint claiming
such fidelity was added, no report approved, and no exhausted recovery repeated.
Neither PR is merged by this change. The production-shipping hold remains.

## Final verification

The exact workflow contract selection passed 1,490 tests with one unavailable local
native-toolchain skip. The combined C++/PDF candidate passed 502 tests plus the
actual frontend-handler wrapper (503 distinct Python checks, no skips). These
include 115 new collection cases; narrower selections overlap.

Independent review first found missing non-runtime transport bindings. The repair
requires the full operation population and exact source/image/configuration/artifact
relationships. All seven original substitutions now fail; 109 independent focused
checks pass. Historical Clang program serialization permits only reordering the
known frozenset literal; unrelated code or member changes are rejected. No execution
program was changed. See verification.json for file and JUnit hashes.
