# Pinned CTU first-use repair

This production optimization applies after the existing placement, header grammar,
header observer, and replacement-index overlays. It changes only `lib/ctu.cpp`.
The installer accepts exactly one complete pinned source variant, verifies the
literal patch and owned native-control hashes, validates the resulting source,
and emits a separate receipt. Earlier overlay identities and receipts remain
unchanged. `expected_prior_repairs` records expected recipe identities; it is not
proof that those scripts executed. Native qualification remains false.

The existing read-only source-call traversal records the first token referring to
each pointer argument. Nested-call matching begins at that exact first use and
preserves original matching, rejection, output order, and one-based ordinals.
Functions outside 8–4096 total arguments retain the original scan. The optional
map is allocated only if a pointer argument exists; allocation failure discards
all partial state and falls back to the original scan for every argument. No
allocation occurs during collection. Branch-sensitive unsafe-usage scans remain
unchanged.

The map uses exact Variable identities and deterministic logarithmic lookup,
with O(pointer arguments) storage bounded by 4096 entries. Small-argument,
early-use, scalar-heavy, or other workloads may see no improvement. This is not a
claim to resolve every template/normal-check timeout or to qualify the assessed
project. Commands, populations, limits, resource policy, and acceptance gates are
unchanged.

`native-controls.cpp` contains only owned synthetic sources and exact expected
CTU serializations obtained from the unchanged baseline. It checks 18 cases,
including mixed argument ordinals, first-use rejection, shadowing, lambda/cast/
conditional/function-pointer/nested/unevaluated uses, threshold/cap boundaries,
and unused/scalar arguments. Five injected optional-allocation failures must
preserve the same records. Two scalar cases permit exactly the mandatory FileInfo
allocation and no optional map allocation. These are tool-build controls, not
assessment evidence or hosted qualification.

Source before: `ad9b01ac6a44f5d5f4101443d550876312b12a17ab11eec332f67b3eb9a85806`.
Source after: `f3e363ae33cb8489ff25f4c1ab7ca02adbf0ee9f5fe1f7d463669e1eaa259ada`.
