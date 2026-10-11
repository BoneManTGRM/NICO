# PR #1712: skip unused alias-scope reconstruction

The next repair defers alias-shadow construction until a typedef replacement
sweep reaches a matching substitution or can mutate tokens. A sweep that reaches
neither barrier now avoids the entire full-list helper scan and scope-tree
construction. The state is local to one declarator; it is rebuilt for the next
comma declarator or typedef. This preserves the published inheritance cache.

Both mutation barriers are necessary: the matching-name branch can remove
qualification before querying alias membership, and the operator-conversion
branch can reach token replacement independently. The first barrier reached
freezes the same token state as eager construction. An explicit initialized flag
retains empty results and prevents subsequent guards from rereading a changed
`typeName`. No pointer-only cache survives into another sweep; `deleteThis()` can
change token contents while preserving its address.

The related endpoint change eliminates the semicolon-order map. It counts full
positions during the existing `findSemicolon` walk, retains the original default
call behavior and excludes missing endpoints. It does not remove the scope scan
for sweeps that still need the helper.

Focused verification: 22 tests passed. The snapshot kernel checks 2,730 event
cases, address-preserving changes, empty snapshots, next-declarator rebuilding,
and 64 unused sweeps with zero helper visits. Five negative controls detect lost
barriers, eager work and stale state. Existing endpoint and inheritance controls
remain enabled. Two independent read-only reviews found no production blocker;
an independently rerun snapshot/endpoint selection passed 10 tests. Review caught
an inline conversion fixture that missed the special operator path; it was
corrected to an out-of-class conversion after a class-local typedef and passed
GCC C++20 syntax checking. Actual native path execution remains unverified.

The exact producer repair applies to all three pinned source blobs. No assessed
source, header observer, deadline, compiler diagnostic, sanitizer finding or
coverage requirement changes. The prior diagnostic patch is reconciled in this
same substantive change: its three code/test files match the supplied patch
blobs exactly, and its test is appended to the current contract selection.
Diagnostics retain bounded primary execution summaries and hashes before
fallback merging; they do not confer completion credit or expose raw commands.

The initial contract selection had 1,982 passes, five skips and one failure in
an unchanged two-second transport child-process deadline test: its child marker
was absent. An isolated rerun plus diagnostic tests passed 89 checks. This
initial failure remains recorded; it is not claimed fixed by the analyzer work.
The final combined configured contract selection passed: 2,004 passed, five
skipped, exit zero in 134.87 seconds. The exact command is the workflow contract
selection, run with the retained workspace Python environment.

No new local full Cppcheck build, Bitcoin replay, image export, destructive cleanup
or paid capacity was used. The preserved binary predates the inheritance repair.
Existing profile totals do not identify the fraction of helper calls that this
change eliminates, so neither a Bitcoin speedup nor timeout resolution is claimed.
Run 38138733322 remains failed at its prior head, with primary 2/15, 12 timeouts,
one AST error and combined 15/577 coverage. Final-head qualification and release
gates are still required before merge or deployment. Original-image identity
remains unproved; skips and small owned kernels earn no native qualification credit.

## Earlier inheritance repair evidence

The analyzer repair groups record aliases by declaring scope and processes all
uses for one target before moving to the next target. Completed inheritance
queries are memoized per target, and base-name resolution is reused within the
immutable helper invocation. Alias declaration and defining type-id exclusions,
complete-class visibility, lexical lookup and existing self-base behavior remain
unchanged. All caches die before subsequent typedef token mutations. Peak cache
storage is bounded by scope nodes and declared base edges.

The previous helper repeats recursive searches through shared inheritance
subgraphs and clears visibility after each change of use scope. The owned layered
diamond demonstrates this defect: the unmodified lookup performs 524,286 base
resolution searches; the candidate performs 70, with 37 distinct completed scope
queries. Querying the alternate root requires only two additional resolutions and
one additional completed scope query.

Focused verification passes 16 checks. The injected production `ScopeInfo3`,
memoization and matching code are compared with the previous lookup contract on
all 1,024 forward inheritance graphs over five records. Controls cover positive
and negative inheritance, multiple targets, member functions, nested scopes,
namespace reopening, sibling exclusion, multiple aliases, defining type-id
exclusion, unresolved direct bases, self-base behavior and cache rebuilding after
owned scope mutation. Negative controls detect disabled memoization, stale target
results and lost defining type-id exclusions. These are owned kernel checks,
not complete tokenization or native project qualification.

A single local measurement ran baseline before candidate in the same process:
40,561 microseconds versus 24 microseconds for the diamond lookup. The whole
kernel exited zero with 0.0478 seconds wall time, 0.0475 seconds user CPU and
9,344 KiB child peak RSS. Cache/order effects and run variance are unmeasured;
these timings do not establish Bitcoin performance. Independent bounded read-only
automated review found no blocking semantic, cache or pointer lifetime issue and
independently passed the 16 focused checks.

The exact configured C++ contract selection, including both kernel modules,
passes locally: 1,977 passed, five skipped, exit zero. Skips earn no native
execution credit. A broader C++ selection returned 2,568 passed, five skipped
and one failure: the owned File API mechanism trial recorded `NOT_RUN` because
`cmake` is absent. No native operation ran in that trial. Its failure remains
explicit and is not fixed or suppressed by this analyzer patch.

The previous run is still failed:
[38129767934](https://github.com/BoneManTGRM/NICO/actions/runs/38129767934).
Downloaded artifact 11701991501 is 19,335,887 bytes; its SHA-256 matches
`fe1a2eb3f59a75859396e4721ca4d9cb34e7cbecf397ae17f36257e46cbfa45e`
and ZIP CRC verification passes. Reapplying the published baseline repair to the
pinned upstream tokenizer exactly matches that run's tokenizer blob
`76e29ba1d332c4195bbca5ed69b4d40fa7179829` and SHA-256
`bc2a39e9ad348b1b1907fbb3a788e682beee47055735a5deb18d0dbd2da157b0`.

The helper still reconstructs the whole scope tree for every matching typedef
declarator. This patch does not establish that inheritance work caused Bitcoin's
90-second timeout, or remove repeated whole-list construction. The prior
instrumentation overhead remains unmeasured. The exact Bitcoin/control
comparison could not run because the retained private reconstruction, analyzer
binary/image, profile and capture receipts are absent from the attached workspace.
The original producer image identity and reconstruction differences remain
unproved. Private source, archives and diagnostic outputs are not included here.

The retained internal AST failure is a separate open case: `src/rpc/client.cpp`
fails at GCC 14.2's `ranges:1935:29`, reporting that `__i` has no AST parent in a
constrained iterator constructor initializer. The retained header's bytes match
its recorded SHA-256. Reproduction and causal diagnosis remain pending.
Compiler context 289 and the UBSan failure at `src/streams.cpp:99:24` remain open;
this repair neither changes Bitcoin nor suppresses those findings.

New kernel regressions join the configured C++ contract job. Publication triggers
the existing qualification workflow; no manual duplicate is needed. Final-head
qualification, image/worker evidence and applicable production/report/delivery
gates must pass before merge and deployment. Assessment scores are unchanged.
