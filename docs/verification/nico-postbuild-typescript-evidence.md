# NICO post-build TypeScript evidence

This change is local preparation for NICO's existing Node CI. It runs the pinned
TypeScript 6.0.3 compiler after the existing Next build attempt and retains a
separate exact-run artifact. It does not activate a production scanner or change
scores, approval, or delivery decisions. The legacy exporter mode is unchanged.

The explicit check disables emission and incremental reuse. It retains the actual
project configuration: `skipLibCheck=true`, `strict=false`, `allowJs=true`, with
`checkJs` absent. Completion therefore does not mean exhaustive semantic coverage
or cleanliness. Diagnostics, including errors, remain in completed evidence;
incomplete capture and absent required Next declarations fail closed.

The record includes compiler/package/Node hashes, lock and configuration hashes,
generated-file hashes, compiler root/program/read inventories, source inventory,
and before/after input checks. Native output is bounded to 8 MiB and stderr to
32 KiB with a 120-second deadline. Failure evidence retains exact bounded stderr
bytes as base64, their hash, exit status, and timeout/truncation flags. The artifact
contains only `typescript.log`, `typescript.json`, and `manifest.json`.

## Provenance boundary

`AuthenticatedRun` is a controller input, not an authentication mechanism. A future
controller adapter must obtain repository, workflow-at-ref, run, attempt, job step
outcomes, source inventory, and artifact metadata independently through authorized
GitHub APIs. Artifact JSON must never construct this context. The validator binds
these observations to exact main/source/workflow SHA and artifact digest, checks
the manifest and native-record parity, and rejects incomplete or conflicting
input inventories. Compiler hashes record identity; they are not a second package
signature verification service. Trust remains in the reviewed NICO workflow,
pinned lock, `npm ci`, and independently authenticated GitHub provenance.

No API adapter or production consumer is wired in this patch. Pull-request
artifacts can be produced for review but cannot qualify as trusted main evidence.
A completed result with compiler errors is retained as completed and not clean.
Build outcome remains an independent field and must not be inferred from clean
TypeScript diagnostics.

## Local verification and remaining experiment

Only owned synthetic source trees use the already installed compiler. Tests cover
real clean/error compiler results, missing generated declarations, changed pins,
symlinks, no source execution/emission, metadata and artifact mismatches, bounded
capture, retained failures, complete native schema, checked generated inputs,
compiler/read identity, and truthful configuration limitations. Existing CI
evidence tests also run. No NICO build, package installation, workflow dispatch,
publication, deployment, or assessment was performed.

Baseline absence tests: 7 failures. Independent review regressions: 5 failures
before fixes (empty native log, discarded stderr, stdout/stderr overflow, timeout).
Final focused suite: **51 passed** in 28.00 seconds, with one pre-existing Python
escape-sequence warning. The exporter CLI also passed a stdlib-only `python -S`
help smoke check, and `git diff --check` passed. Independent read-only review
confirmed the corrected evidence boundaries. Raw logs are retained outside Git
under `/tmp/nico-ci-typescript-*.txt`.

The minimum real experiment requires separately authorized publication and one
ordinary exact-main CI run. Independently retrieve run/attempt/workflow/job/artifact
metadata and source inventory, verify the artifact digest, import its exact ZIP,
and inspect diagnostics, generated-file participation, settings and build/check
outcomes. Confirm captured runtime budgets accommodate the real project. Do not
infer production scanner integration, score recovery, or readiness from synthetic
tests alone. Publication and rollout remain with the parent owner.
