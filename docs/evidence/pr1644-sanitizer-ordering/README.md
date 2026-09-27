# Native timeout and CLI artifact-root correction

This candidate continues PR #1644 from dc2521cb. It repairs two independently
verified problems in full native run 36272142582, which finished FAILURE on
September 26, 2026 at 23:05 UTC. Its producer is the PR merge checkout
`a65f40441f597fce702bdbce37332651780fa3c7`, not the branch SHA.

## Retained evidence

Artifact 10918006148 is 20,291,676 bytes. Its verified ZIP SHA256 is
`d79dd0536821971869309baf3f521769657f1cf41994544638c8bdce043d0af9`.
Every extracted member agrees with the ZIP. The original v2 receipt SHA256 is
`dd2c89b212e2b050921901005d54bae2980fb2f50fb8bfab782df42972483e47`.
Compiler/static reconstruction and the original runtime summary agree exactly.

| Population | Retained result |
| --- | --- |
| Baseline | 377/377 passed |
| Compiler | 475/475 checked |
| Static analysis | 475/475 required contexts analyzed |
| Functional | 6/6 passed |
| ASan | Real stage timeout; completed JUnit population unavailable |
| UBSan | Not executed |
| Fuzz replay/campaign | Not executed |

The ASan command timed out after 900.046 seconds, exit 124. Its untruncated
63,111-byte log has 377 starts and 376 Passed completion lines. Only
coinselector_tests was unfinished. These progress lines do not replace JUnit or
grant completed-population credit. CTest had not written its final JUnit; the
retained FileNotFoundError explains the secondary artifact-unavailable error.
First and terminal failure both remain runtime-address-tests. No OOM event was
recorded; scratch remaining was 3,652,853,760 bytes. These facts do not prove a
particular CPU-contention cause or production qualification.

## Corrections

The CLI accepts relative output directories but its final artifact reader requires
an absolute root. `Path.absolute()` supplies that root without resolving symbolic
links, preserving descriptor-based no-follow reads. Eight CLI cases replay real
retained fixture evidence through argument parsing, storage, validation and decision
writing. Both failing relative-path cases fail before the correction and pass after
it; absolute controls and symlink rejection remain intact. With the corrected reader,
the real incomplete ASan run still rejects with worker_runtime_collection_incomplete.

Runtime plan v4 adds explicit ASan scheduling costs for every suite whose retained
ASan time in completed run 36250553285 was at least 25 seconds (16 suites). Values
are rounded to milliseconds and bound in the plan and exact wrapper arguments.
The generated build's top-level CTestTestfile.cmake receives only documented COST
properties, after its existing subdirectories. CTest ignores names absent from that
test population; no test is added or selected by the hints. Source files, binaries,
instrumentation, test commands, result parsing and qualification gates are unchanged.
No execution count or successful result is seeded. Estimates are scheduling metadata.

The write refuses linked directories, linked or multiply linked files, nonregular
files, oversized/empty metadata and repeated application. Historical v1-v3 plans
retain their exact old wrapper and arguments. UBSan retains the old wrapper. Tests
still use parallelism 2, case deadline 300 seconds, stage deadline 900 seconds and
the original aggregate/resources. Fuzz scheduling remains unchanged.

Official COST semantics: https://cmake.org/cmake/help/latest/prop_test/COST.html .
Owned real-process controls use the exact workflow CTest 3.31.6 wheel (SHA256
`1c8b05df0602365da91ee6a3336fe57525b137706c4ab5675498f662ae1dbcec`). They verify
that long suites start first while membership, commands and all non-COST properties
remain identical. Genuine failure and timeout still return exit 8 with failed JUnit.

## Limits and remaining acceptance

An illustrative two-worker model using retained timings predicts about 891.7 seconds
after reordering versus 910.9 seconds in original order. The unfinished case uses
its historical duration, and rounded progress timings omit overhead and variability.
Only about eight seconds of modeled margin remains. This is not a performance pass
or a promise that the next full run will finish. Actual published-candidate native
evidence is required; timeouts and missing work remain failures.

The historical UBSan net_tests finding from earlier complete runs remains unresolved
and retained. Completed collection is separate from target-test success. No image
promotion or production qualification is granted. PR #1645's exact failed-report
input acceptance remains unmet because the historical renderer context was not
durably retained. Neither PR is merged by this correction, and production is unchanged.

Verification counts, hashes and independent review are in verification.json.
native-revalidation.json retains the reconstructed current failure. revalidate.py is
the data-only reproduction used with the original archive and extracted workspace;
it runs no assessed code and does not modify the archived receipt.
