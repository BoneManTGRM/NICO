# Local template subphase measurement

Review-only base: 63f4e03068a386eddda4dc31c41e9f5d4b24579d. No hosted
run, assessed input execution, publication, production recipe, workflow, scheduling
test, deadline, parallelism, isolation control or acceptance rule is changed.

The preceding grouping candidate failed hosted run 38440312426 on merge
dd37bb4bc83296d0cd58041eec5c8257f722b677. Parent-retained evidence reports
basic.cpp and bitcoin-node.cpp each exit 124 at 90063 ms; stdin exit 0 at
114 ms. Build/binding/owned observer controls passed. Artifact 11835322140,
10904671 bytes, SHA256 a76531c289da2265c798928941f8484e45ce7b51fff8b6d9ba340b1cda3880d9,
64 CRC-valid members, is retained as Library libfile_530ed00660408191afaa42d60f21229a
version 0. This local change neither removes findings nor establishes an improvement.

## Measurement contract

The source-pinned additive overlay places entry scopes in
simplifyTemplateInstantiations (selection remainder), matchSpecialization,
expandTemplate and replaceTemplateUsage. Function entry covers both normal and
specialized fallback call sites. Each scope restores its caller's active bucket
and depth on normal returns, early returns and C++ exception unwinding. Four
thread-CPU buckets are exclusive: transitioning into a child charges its parent
through the transition; the child never contributes again to parent CPU.

Entered calls, normally completed calls, loop-body visits and the existing
successful-declaration counter (`instantiations`) are distinct quantities.
Completion means a scope exits without an active uncaught exception. In the
pinned C++11 build this is deliberately conservative: a normally returning call
made during unrelated exception unwinding is not counted complete. Exceptions
are neither intercepted nor suppressed. No destructor runs after SIGKILL.

Seven visit counters cover the live instantiation selection loop, specialization
group and argument-token loops, expansion outer and body walks, replacement
whole-list walk and replacement nested instantiation scan. Count at loop-body
entry before filters/mutations. Visits are not token counts: link skips can span
multiple tokens, the same token may be visited repeatedly, and a nested loop is
counted separately. This does not measure every inner expansion helper.

No list snapshots, token pointers, token strings, cached matching decisions or
additional token traversal are introduced. Existing append/erase/retargeting,
first-match behavior and order remain intact. Stripping insertion markers restores
the exact grouping input bytes; header changes contain only measurement code.

State is fixed-size thread-local counters plus fixed per-call automatic scopes.
The enabled path performs saturating integer increments per visit, clocks at
function transitions and one coarse checkpoint per 4096 counted operations.
No per-token clock, per-token output or measurement allocation is added.
Disabled operation calls neither the clock nor output and changes no counters.
The original 128-record, 1024-byte and one-second output caps remain, including
only the existing three first-entry exceptions to the rate limit.

A checkpoint charges the active bucket before emitting. Thus retained snapshots
include unfinished work and active depth, not just completed calls. Long helper
calls with no instrumented checkpoint can leave an unobserved tail. Record caps,
output truncation and termination still make evidence partial; no destructor or
signal handler is used to force a final record.

`wall_us` remains monotonic wall time; `cpu_ticks / clock_scale` remains process
CPU (`-1` means unavailable). New `*_cpu_ns` fields are exclusive thread CPU from
CLOCK_THREAD_CPUTIME_ID. `thread_clock_status`: 0 unattempted, 1 available,
2 unavailable/sticky failure. A missing/failed/backward clock never falls back
to process time or wraps a delta; previous valid totals remain partial. The
clock call preserves errno. Instrumentation costs are included in measured CPU.

## Versions and identity

New output is NICO_STAGE_V2. V1 retained evidence remains parseable using its
original field layout and evidence schema. Mixed versions, unknown complete
versions, wrong expected versions, invalid fields, bound violations and regressing
per-lane template totals fail closed. Partial final records retain only the
validated prefix, marked incomplete; they are not invented as complete records.

Runtime binding advances to nico.stage-runtime-binding.v3 and binds integer
record_version=2 along with new exact header, overlay and composed-source hashes.
The collector supplies this expected version. The unchanged production recipe
is used only to derive a distinct diagnostic recipe. Old runtime bindings do not
qualify the new measurement, while old evidence can still be read explicitly.
No new runtime-image binding is claimed by this local validation.

## Owned validation and limitations

Run local contracts with the existing environment:

    python -m pytest -q tests/test_native_template_subphases.py tests/test_native_stage_counters.py tests/test_native_specialization_groups.py tests/test_native_timeout_diagnostic.py tests/test_cpp_project_static_stage.py

The new owned native fixture requires the installed /usr/bin/g++-14. It uses
C++11, -O2 and deterministic injected thread time to check nested same/different
buckets, early return, exceptions, unfinished snapshots, disabled absence,
clock failure/backward time, saturation, rate/record caps and live list mutation.
Parser and runtime-binding negative cases run alongside these tests. The clock
injection is a compile-time owned-test hook, absent from the analyzer recipe.
No workflow test command was changed; review must account for the new native
fixture's compiler prerequisite before any future publication.

First contract attempt: 220 passed, 2 failed (old source-fragment fixture lacked
new insertion anchors; old collector fixture omitted its explicit V1 version).
Both unsuccessful results remain retained. Updated fixtures preserve their
original assertions. Expanded contract run: 229 passed in 5.06 seconds; final receipt records the
additional clock-metadata checks: 231 passed in 4.19 seconds. Final partial-record
validation checks brought the final suite to 234 passed in 5.19 seconds.

A bounded real-clock owned workload measured 2000000 visit increments plus
100000 nested scopes, with identical checksum enabled/disabled, three interleaved
runs of each. Internal wall time: enabled 36.08–37.89 ms, disabled 4.12–4.42 ms.
This is approximately 8.6 times the median on extremely cheap synthetic work,
not a measured analyzer overhead ratio or a performance improvement. Frequent
function transitions can materially perturb a deadline-limited run. All six
runs exited zero; disabled stderr was empty. Build and per-run logs are retained
outside the patch in /workspace/nico-subphase-validation.

A hotspot remains undiagnosed. Even a future large replacement CPU bucket plus
many nested visits would not prove that those visits dominate replacement CPU.
No observer-library or hosted-image equivalence follows from local owned tests.


The full local clean analyzer/owned-test build passed once in 114.780 seconds
within the 300-second build budget (GCC 14.2.0, -O2 -DNDEBUG, j2, pinned tools).
All 253 exact owned template case names passed with 0 failures and 12 existing
TODO assertions, both disabled (1.619 s) and enabled (1.618 s). Combined owned
test time was 3.236 s within the original 180-second test budget. Enabled stdout
and non-counter stderr were byte-identical to disabled. Four V2 records parsed;
they include partial totals, not a final exhaustive snapshot. Two entered calls
in the last snapshot lacked normal completion, consistent with exception paths;
this is not a new analyzer finding. These timings are not a controlled analyzer
overhead estimate. No full hosted observer control was rerun locally.
