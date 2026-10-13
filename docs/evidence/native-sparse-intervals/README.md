# Sparse template interval accounting (local review only)

This replaces the held per-transition timer design on a separate local branch.
Commit c571221de8624d6c4809b5dee62259553e988e25 and all its retained results remain
unchanged. The underlying candidate still starts at 63f4e030. No Bitcoin or other
assessed input, hosted run, publication, deployment or purchase is part of this
validation. Existing findings and the failed grouping outcome remain recorded.

## Accounting contract

The same four function-entry guards now perform only state/counter operations.
Every entry and exit increments a saturating transition ID, including same-phase
nesting. The guard restores prior phase/depth on return and exception unwinding;
it never restores the transition ID. Entered calls, normally completed calls,
seven loop-body visit counters and successful declaration calls remain distinct.
The C++11 completion check remains conservative during unrelated unwinding.

Only an accepted checkpoint calls the thread CPU clock, at most twice. Suppressed
attempts and record-cap exhaustion do not read it. Original output bounds remain:
128 records, 1024 bytes each, one-second spacing except the same three first-entry
allowances. Operation checkpoints remain every 4096 visits; scope guards do not
perform clocks, logging, allocations or extra token/list traversal. Existing
non-thread-clock rate-gate overhead is not eliminated.

A checkpoint reads CPU before formatting/flushing and after it. A new interval
runs from the previous post-checkpoint reading to the current pre-checkpoint
reading. It belongs to a phase only if phase AND transition ID are unchanged.
Transitions away and back, including same-phase nested calls, make the interval
mixed: all its CPU remains in unattributed_ns. A stable phase 0 interval is
outside_ns, never silently assigned to a template phase. These are observed
unchanged-phase intervals, NOT exhaustive exclusive phase CPU or CPU percentages.

observer_ns records the bracketed checkpoint cost and is reported one record
late. The latest post timestamp/cost is unavailable if no subsequent record is
retained. Clock-read and bookkeeping prologues/epilogues and suppressed output
attempts can still contribute residual observer cost to intervals. A transition
during observer processing invalidates the next interval baseline. This is a
synchronous thread-local design; it adds no signal handler or asynchronous probe.

Interval kind: 0 prefix/invalidated baseline; 1 selection; 2 matching; 3 expansion;
4 replacement; 5 mixed or transition-saturated; 6 outside; 7 unavailable clock.
The first prefix and final tail are always unknown. Long helpers without
instrumented visits can leave long unsampled tails. Operation-driven sampling is
biased toward paths reaching those visits; absence of attributed CPU exonerates
no phase. Visits count loop entries, not distinct tokens, work cost or CPU shares.

Transition saturation is sticky and disables stable attribution; equality at the
maximum is never treated as unchanged. CPU/call/visit sums saturate, never wrap.
Thread-clock status is 0 unattempted, 1 available, 2 sticky unavailable/backward.
Clock failure invalidates the baseline, leaves prior totals partial, and does not
substitute process CPU or zero for an unknown interval. Wall microseconds and
process CPU ticks/scale retain their original distinct meanings.

## Version and source binding

Output is NICO_STAGE_V3. Its stable_*_ns and interval fields have separate names
and interpretation from V2 exact-per-transition timers. Retained V1 and V2 records
remain readable under their own schemas. Runtime binding V4 requires integer
record_version=3 and the new exact header/overlay identity. Old bindings or mixed
record versions cannot satisfy it. The parser rejects invalid phase/depth,
completion counts, clock/read bounds, transition saturation, backwards totals,
false stable attribution, inconsistent interval totals and malformed records.
Partial records retain only validated prefixes with explicit incompleteness.

Generated token source and additive insertion sites are unchanged from c571221;
the header changes accounting semantics only. Source stripping must still restore
the pinned grouping inputs exactly. No production recipe, workflow, scheduling
test, analyzer decision, resource bound, isolation rule or acceptance criterion
is changed. New native unit controls require the existing installed GCC 14.

## Owned overhead gate

Same cheap workload: 2000000 visit operations and 100000 nested scope calls,
GCC 14, C++11, -O2, identical environment/order and checksum, three enabled and
three disabled runs. Clock-read/transition totals are printed AFTER the timed
section. The probe does not run an assessed repository.

Previous held median: enabled 36.871535 ms, disabled 4.281094 ms, ratio 8.61264.
Sparse median: enabled 10.200802 ms, disabled 1.555859 ms, ratio 6.55638.
Sparse enabled range 5.399699–11.779616 ms; disabled 1.468732–1.808500 ms.
All six sparse runs exited zero with matching checksum. Enabled runs each made
2 thread-clock reads and 200002 guard transitions; disabled runs made zero.

Enabled absolute time fell 72.3%, incremental enabled-minus-disabled time fell
73.5%. This material absolute reduction plus passing controls justified ONE
local pinned analyzer build capped at 300 seconds. The ratio remains material,
the short timings vary, and the disabled timing changed. This is not a controlled
Bitcoin/analyzer overhead bound or evidence of a performance improvement.

Deterministic controls cover nested same/different phases, mixed and stable
intervals, early returns, exception unwinding, unchanged live-list mutation,
unfinished snapshots, pre/post clock failure, backward clocks, sticky saturation,
observer exclusion/baseline invalidation, disabled absence, no clocks on suppressed
checkpoints, record caps, and worst-case record width. Parser/binding controls
also retain legacy-version interpretation and reject invalid V3 attribution.
Actual validation receipts and all attempts live in /workspace/nico-sparse-validation.

## Actual local analyzer result

One build passed in 122.075432 s within 300 s, pinned GCC 14.2.0, j2,
-O2 -DNDEBUG. Both 253-case owned runs passed with 0 failures, 12 existing TODOs,
exact expected names and byte-identical stdout/non-counter stderr. Disabled wall:
1.568989 s; enabled: 2.602594 s (about 1.66x). Child CPU: 1.539402 s versus
2.497677 s (about 1.62x). This single non-interleaved pair is not a causal overhead
bound, but it is a MATERIAL unresolved observation, not evidence of negligible
cost. No repeat was used to replace it. Total owned test time 4.171583 s stayed
within the original 180-second budget. Python/source contracts: 251 passed.

Four V3 records parsed. Last retained snapshot: 7 thread-clock reads, 4062 scope
transitions, clock available, no transition saturation. There is one post-record
read per accepted checkpoint; normal source flow therefore implies 8 reads in
all, with the final post-read not represented in the last record. All four stable
phase totals were zero. Unattributed CPU 1728978745 ns, outside CPU 69298 ns,
lagged observer CPU 230049 ns. No unavailable-clock interval appeared in these
four records; the unobserved prefix, final tail and final observer cost remain
unknown. This illustrates the intentionally conservative accounting, not a
hotspot diagnosis. Hosted observer/runtime equivalence remains unverified.

The candidate stays local for independent review. The owned-suite timing concern
must not be hidden by the cheaper probe's improved result. No claim about Bitcoin
or timeout improvement is supported by this validation.
