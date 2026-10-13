# Diagnostic grouping composition (local review)

Base: 6243d46bed6ba7e84b54f974ab9459ffa2f548f7. Remote diagnostic tip and
base 2bd1ea9dac2d38b721661eab68a26ef7d9747e33 were rechecked before editing.
The scheduling correction is not included. No push, native build, analyzer
execution, assessed input, workflow launch, merge or deployment occurred.

The original candidate patch is SHA256
f8d5989c168ef48f065fc262e7de42bf1611f71b740914608ca0ed6f7e98c14f.
Its overlay script was relocated byte-for-byte to
scripts/native_stage_counters/specialization_groups.py, SHA256
09cd155550eddb1518520bd875e314dd6cd08283c52c643ce303d523fa0011c8.
The Python source-contract tests use the new import/path, omit the native
synthetic C++ execution test, and restrict the production-wiring assertion to
Dockerfiles. Native behavior is covered by the separately gated real fixtures.

## Composition and authentication

Production repairs (AST, header grammar, observer) precede grouping, which
precedes additive counters. Grouping retains its three exact input pins.
Grouping output templatesimplifier SHA256:
d77673074aa057005844006f6a8e7a97a3320155c2e538635463e2ab82028d13.
Combined output SHA256:
80715d5d7e76777f19779648afa82b78cd290f08786220f23360cb39157425c7.
Combined overlay identity:
cb505b6b0bb207d30529627c19dff93146baa404658325d2625c371ca3cd1721.
Diagnostic recipe SHA256:
5f62ba32d38c602fb56d3c4d513a104ea61c2549f85a5883a7052c65959e507c.

Source-only transformation on verified retained inputs confirmed exact output
hashes, counter stripping back to grouping, rejection of reversed order and
real owned-fixture patch application. The source trees used for these checks
are private evidence, not part of this package.

Runtime binding v2 separately validates the grouping receipt, combined source
hashes copied from the stopped candidate container, overlay identity and
recipe identity. Original archive/tool/observer authentication stays intact.
It captures a new compiled binary hash and verifies that hash in the sandbox.
Known original, prior instrumented and local uninstrumented binaries are
explicitly rejected; this blacklist supplements the trusted build/recipe chain.
Counter instrumentation remains additive relative to the semantic grouping
source, not relative to the pre-grouping source. No new binary exists yet.

## Owned regressions and local tests

owned-fixtures.patch is the exact reviewed 3348-byte patch, SHA256
1325897d39c0de3d25b17579337948b66ee95c0d8ae96f1d6794e1626e0d093e.
The pinned case-name manifest enumerates 253 exact cases. A future explicit
owned_regressions invocation accepts only a fresh trusted private composed
source tree, requires the pinned local compiler/make identities, rejects old
objects/binaries, forces a two-job rebuild with an allowlisted environment,
and retains build/test failures and process-group cleanup results. Budgets are
300 seconds for the combined build and 180 seconds for tests. This harness is
not invoked by the workflow in this patch. It is intentionally local-tool
specific; another toolchain needs separately reviewed identity changes.

The third added fixture repeats eight fresh tokenizer runs. It does not prove
within-run multi-pass state behavior. Twelve existing TODO assertions remain
known limitations; the harness requires and records them, not suppresses them.
The standalone grouping candidate previously passed real regressions; the
new grouped-and-instrumented binary has NOT been built or tested.

Python/source-contract command (no native compilation/execution):

```
timeout 120s /workspace/nico-venv/bin/python -m pytest -q tests/test_native_stage_counters.py tests/test_native_specialization_groups.py tests/test_native_timeout_diagnostic.py tests/test_cpp_project_static_stage.py
```

Retained attempts: 1 had 194 passes/1 failure (copied wiring assertion matched
new test filename), plus an existing invalid-escape SyntaxWarning. After its
correction, attempt 2 passed 197 in 4.32s. Additional failure-retention checks
passed 199 in 4.19s (attempt 3); final mocked-tool portability adjustment passed
199 in 4.33s (attempt 4). All logs remain private evidence.

## Trigger and release boundaries

Production Dockerfile, full-qualification filters, artifact authentication,
three-case selection, 90/540-second limits, resource controls, owned runtime
controls and cleanup are unchanged. New paths do not match full-qualification
filters. The diagnostic workflow change only adds source-contract tests, but
publishing it on the matching diagnostic PR can immediately trigger the
existing diagnostic. Publication and launch therefore remain separate approval
gates after composition review and composed owned regression validation.
No recovered Bitcoin source, binaries or private runtime evidence is packaged.
