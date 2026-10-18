# Parallel depth-list hash probe

Base: `7f100b0261172dd70aba225ff72400913a5ea54e`.
Tested `nico/comprehensive_run_record.py` SHA256:
`684a3661db432b6acfaab3aa99d8385c815f58fc49f285b45658354ba27e4e16`.

Only `_bounded_native_json` changes: parallel value/depth lists replace per-entry
tuples and generators. The traversal order, node/byte budgets and fallback are
unchanged. It still rejects containers at `depth >= max_depth`; the caller still
passes `max_depth=64-len(ancestors)`. Thus native eligibility requires relative
container depth plus ancestor count below 64. This preserves the recursion
correctness repair in PR1787 rather than reverting to the earlier unsafe probe.

## Existing verification

All 228 tests passed on Python 3.12.14 and 3.11.17, each file in an isolated
process. Exact file names, counts and exits are in `python312-tests.json` and
`python311-tests.json`; each `name` denotes `tests/test_<name>.py`, invoked with
`python -m pytest -q`. The 37 bounded-hash cases include the remaining-depth,
standard-stream recursion failures, digest compatibility and large-container
memory regression. No regression was removed or weakened. The compatibility suite was rerun after the alignment correction. Benchmarks
were not rerun.

Python 3.11 used existing offline image
`sha256:356ca30e80a5ad131c87df67767fbd43f0e510b7cab9ae7f20bf8ed58b520127`,
network disabled, read-only source/root, UID10001, capabilities dropped and
no-new-privileges. No dependency installation was required. The tested snapshot
and committed Python file are byte-identical.

## Allocation measurements

The existing 12,000-entry large-container hash test measured 77,433 bytes of
extra peak allocation on 3.12 and 77,601 on 3.11, below its 1,048,576-byte limit,
with matching reference digests. Accepted 8,191-element list probes peaked at
196,664 bytes; accepted 4,095-entry dictionary probes peaked at 196,640/196,656.
Oversized 8,192-element lists and 4,096-entry dictionaries were rejected before
expansion. See the two allocation JSON files. These are measured fixture peaks
from tracemalloc, not total RSS, input-storage costs or universal bounds.

## Saved timing evidence for the prior variant and limits

The prior, pre-alignment-correction candidate was timed against depth-correct
current code. That experiment measured
724.353/665.269 ms median wall time and 723.615/664.679 ms CPU: **59.085 ms,
8.16% synthetic component improvement** for that earlier variant. The corrected
candidate has not been benchmarked; this number is not a measured improvement
for the current corrected source. Probe calls and visited nodes matched
(20,005 and 2,540,015). Deep-small current/candidate wall time was
1.3486/0.9899 ms, with 64 probes and 2,144 visited nodes in both.

`saved-component-timings.json` retains that experiment: `baseline` denotes the
depth-correct tuple stack and `current` the then-uncommitted parallel-list
candidate. Both SHA labels name the checkout base, not two committed variants.
Python 3.12.14, CPU affinity `[0]`, GC enabled, one correctness pass and warmup
per variant, four samples each in ABBA order; memory/traversal instrumentation
ran separately. The 48,760,011-byte synthetic fixture has depth 9 and shared
message strings; it is not a production-record replica.

For context, an earlier, separate pre-PR1787/current experiment measured
540.606/718.450 ms wall and 539.996/718.009 ms CPU on that wide fixture,
approximately 32.9% overhead for correct depth accounting. Its deep-small
baseline/current was 0.0507/1.3287 ms; the earlier baseline incorrectly bypassed
the required standard fallback and must not be restored. Do not combine
separate timing pairs as if they were one controlled run.

There is **no demonstrated production download speedup**. Production phase
spans overlap, and these synthetic effects do not explain the observed
12.374-second production hash or full retrieval latency. No caching, retained
artifact reuse, approval-policy, report, roadmap or Spanish changes are included.


## Mid-probe source mutation correction

The initial parallel-list implementation read the source length after copying
values. A deterministic trace hook clearing a plain list or dictionary after
`pending.extend` reproduced `IndexError: pop from empty list` in all three
list/key/value cases. Depth entries now use the actual private stack delta,
`len(pending)-pending_before`, after extension. They never use a second mutable
source-length read to count already-copied values.

The three new regression cases fail on the original candidate and pass with the
correction. `mutation-baseline-control.json` records a separate deterministic
control: both the paired-stack baseline from 7f100b and the corrected candidate
return true after clearing the source at equivalent after-copy barriers. The
trace hook is always restored. This tests internal stack alignment only; it
introduces no snapshot or arbitrary concurrent-mutation guarantee. Iteration
order, remaining-depth condition and all budgets are unchanged. The allocation
measurements above were repeated for this corrected source and stayed unchanged.
