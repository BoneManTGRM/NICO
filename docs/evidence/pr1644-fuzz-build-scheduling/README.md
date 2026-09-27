# Bounded fuzz build scheduling after the completed native timeout

Full Bitcoin run [36241917330](https://github.com/BoneManTGRM/NICO/actions/runs/36241917330)
on `3cbe70235948e3a89ff44a71418524a6ddad7171` completed with failure on
2026-09-26 at 14:43 UTC. Artifact 10908257917 is 20,828,797 bytes, SHA-256
`0bd6093eb42d40f6cf99fa0a282a518a31b61b8f489f12075a80f8c2a1fa5e67`.
The retained source, compiler contexts, static outputs and runtime operations were
hash-checked and reconstructed. The original runtime summary compares exactly
before and after this correction.

Baseline 377/377, compiler 475/475, static contexts 475/475, selected functional
6/6 and ASan 377/377 completed successfully. UBSan executed all 377 tests and
retained the same failed `net_tests` diagnostic at `src/streams.cpp:99` (376 passed).
The 31,873 static observations are not confirmed vulnerabilities.

The corrected Clang/GCC configuration got past the earlier `mpgen` link failure.
The serial fuzz build then timed out after 1200.132 seconds, exit 124, with
untruncated output ending at the displayed 76% build step (`coins_view.cpp.o`).
That percentage does not estimate remaining wall time. Neither required replay
nor the campaign ran. The first failure remains `runtime-undefined-tests`; the
terminal operation is `runtime-fuzz-build`. See native-result.json and the
digest-bound native-fuzz-build.txt for the exact retained result.

Runtime plan v3 separates build scheduling from campaign scheduling. It requests
`min(2, scope.parallel)` fuzz compile workers instead of one. The campaign stays
single-process. Historical v1/v2 plans retain their exact serial build commands.
Plan reconstruction and evidence validation bind the version and actual native
arguments, including rejection after a forged plan digest is recomputed.

This changes no source, corpus, population, sanitizer, compiler, build target,
1200-second build deadline, 6000-second runtime deadline, or sandbox resource
ceiling. The next full run must prove build/link completion, actual replay and
campaign execution, and acceptable memory use. The previous whole-run peak of
10,852,225,024 bytes under the 12-GiB limit is not a fuzz-specific headroom
measurement and does not prove the new schedule fits. Timeouts, failed replays,
UBSan results and incomplete qualification remain failures.

The exact workflow contract selection passed 1,375 tests with one local native
toolchain skip. The focused selection passed 237, including 24 new cases.
An independent reviewer found no blocking code defect and passed 45 affected
tests. Counts overlap. The identical new test file against unchanged f32c8cda
produced 20 failures and 4 passes; most failures demonstrate the missing v3
contract, not 20 independent native timeout reproductions. The real timeout is
established by the retained full run. Verification metadata includes source and
JUnit hashes. Combined with PDF c6f9f4c, 388 distinct Python checks passed,
including the actual frontend-handler wrapper (no skips). Both source ledgers
were retained. These integration checks use fixtures, not the blocked actual
assessment input. Local tests and data reconstruction are not new Bitcoin execution.

The owner's merge authorization remains valid. Merge still requires the applicable
native evidence and actual-input report acceptance. PDF PR #1645 remains at
`c6f9f4c7ad53c791d53e0a10dcb303e190078394`; both of its normal NICO CI event paths
passed. The supported authenticated review/recovery UI supplies no retained-input
export for the blocked assessment without operator approval. No approval was
manufactured, no repeated continuation was issued, and production is unchanged.
