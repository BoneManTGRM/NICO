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

`AuthenticatedRun` is a controller input, not an authentication mechanism. The NICO GitHub
adapter obtains repository, workflow-at-ref, run, attempt, job step
outcomes, source inventory, and artifact metadata independently through the existing App-aware metadata client and authorized
GitHub APIs. Its public entry point accepts only archive bytes and expected IDs,
never an externally supplied authentication context. The private injected-client
seam is for trusted controller code and owned fixtures only. Artifact JSON must never construct this context. The validator binds
these observations to exact main/source/workflow SHA and artifact digest, checks
the manifest and native-record parity, and rejects incomplete or conflicting
input inventories. Compiler hashes record identity; they are not a second package
signature verification service. Trust remains in the reviewed NICO workflow,
pinned lock, `npm ci`, and independently authenticated GitHub provenance.

The metadata adapter is implemented; no production scanner consumer is wired in
this patch. Pull-request
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
ordinary exact-main CI run. Call `import_current_nico_ci_evidence` with the exact archive bytes and expected
SHA/run/attempt/artifact IDs using the existing authorized controller credential;
verify the independently fetched metadata and digest, import its exact ZIP,
and inspect diagnostics, generated-file participation, settings and build/check
outcomes. Confirm captured runtime budgets accommodate the real project. Do not
infer production scanner integration, score recovery, or readiness from synthetic
tests alone. Publication and rollout remain with the parent owner.


## Authenticated metadata adapter

`nico/nico_ci_typescript_github_v1.py` fixes the API origin and NICO repository.
It rejects anonymous clients, non-main or superseded runs, prior attempts, runs
older than seven days, expired artifacts, substituted repository IDs, workflow
paths, commits, artifacts and source blobs. It brackets capture with current-main,
latest-run/attempt and artifact rechecks. Attempt-specific jobs must report a
successful checkout and upload; actual build and check outcomes remain separate.
GitHub's job response need not repeat the attempt number: the authenticated
attempt-specific endpoint binds it, and any supplied conflicting number is rejected.

The adapter hashes independently fetched Git blobs and matches the full inventory
against the retained record. The workflow, collector, exporter and helper must
also match the reviewed controller copy byte-for-byte. Matching GitHub metadata
alone does not approve a substituted workflow. Generated inputs, effective config,
compiler identity and diagnostics remain subject to the existing importer checks.
Authenticated incomplete records preserve their bounded failure diagnostics and
stderr separately; they never count as completed or clean. Truncated native JSON
is retained as failure evidence without parsing it as successful output.

The adapter limits requests to 1,500, source bytes to 128 MiB, individual blobs to
8 MiB, and checks a 600-second budget before and after requests. It fails closed
on truncated source/job listings. The existing shared client buffers each JSON
response before adapter checks; this is not a hard HTTP response-memory bound.
The adapter does not download artifacts or invoke builds. The supplied ZIP is
untrusted until it matches the independently fetched artifact digest.

The public factory reuses `MetadataAuthGitHubAssessmentClient`, including its
normal existing GitHub App installation-token refresh or configured server-token
fallback. No local credential was inspected, factory instantiated, permission
changed or token configured during this work. Production must already authorize
this repository with **Actions: read**, **Contents: read**, and repository metadata
access. Missing authentication or API access returns incomplete. No write or
workflow-dispatch permission is needed. These are endpoint-derived requirements,
not a claim that production permissions were tested. See the official
[Actions run API](https://docs.github.com/en/rest/actions/workflow-runs),
[artifact API](https://docs.github.com/en/rest/actions/artifacts), and
[Git blob API](https://docs.github.com/en/rest/git/blobs).

Actual GitHub payload compatibility, artifact ZIP digest behavior, available
permissions and total capture latency still require the authorized real-run
acceptance. Approximately one blob read per distinct tracked input is needed;
rate limits and the capture budget can yield an honest incomplete result.

Adapter final verification: **86 passed** in 52.77 seconds across the adapter,
evidence exporter/importer and existing CI-evidence suites; one pre-existing
escape-sequence warning. Baselines recorded 21 missing-adapter failures, one
incomplete-diagnostics retention failure, and one final-response deadline failure.
Independent read-only review found no remaining provenance blocker after the
deadline correction. Logs: `/tmp/nico-ci-adapter-red.txt`,
`/tmp/nico-ci-adapter-incomplete-red.txt`, `/tmp/nico-ci-adapter-deadline-red.txt`,
and `/tmp/nico-ci-adapter-final-green.txt`. Main was rechecked at
`86e66391af6cacb28af467d6bf35a768f0f00046`; the dormant prototype is unchanged.

## PR 1740 portable-test follow-up

The initial tests used a fixed executor-only compiler path and skipped when it
was absent. Baseline portability controls recorded 2 failures and 1 skip. Tests
now resolve TypeScript from the actual checkout, or an explicit absolute
`NICO_TEST_TYPESCRIPT_ROOT` override validated against package metadata and the
reviewed 6.0.3 lock pin. Missing dependencies fail clearly. The hosted test shards
already install frontend dependencies; that step now uses lockfile-based `npm ci`
with scripts disabled, and Node 24 matches the evidence-producing job.

Using the already installed compiler via the explicit local override: **90 passed,
0 failed, 0 skipped** in 53.61 seconds. With no override and no checkout dependency,
the selected compiler test produced the expected **0 passed, 1 failed, 0 skipped**
(52 deselected). No local install or real build ran. Independent read-only review
found no portability blocker. Logs: `/tmp/nico-ci-portability-red.txt`,
`/tmp/nico-ci-portability-green.txt`, and
`/tmp/nico-ci-portability-missing-dependency.txt`.

Production exporter diagnosis remains pending. The supported GitHub connector
returned artifact 11940972983 for run 38666299200, but its returned file could not
be materialized: the workspace proxy returned 403 Forbidden. No ZIP bytes,
manifest or failure reason have been verified locally. The reported Next config
rewrite is still a lead, not an established artifact-backed cause. No production
exporter guard was changed, and this follow-up remains local pending artifact
materialization and diagnosis.

## Build-log-supported configuration candidate

Node.js CI run 38666299200 checked out synthetic merge
`f27fa17c97f558dd32dd3a7d4085502f968eb391`. The retained job log records a successful
Next 16.4.0 build and subsequent `tsc --noEmit`, with Next changing tracked
`tsconfig.json` to `jsx=react-jsx` and adding `.next/dev/types/**/*.ts`. Source-only
inspection and real owned Git fixtures establish that the published exporter
rejects either edit before invoking its compiler, once repository/SHA checks pass.
The original artifact failure reason remains unverified because materialization
was denied; no artifact-download retry was attempted.

The candidate explicitly commits only those two configuration requirements.
Strictness, `skipLibCheck`, `allowJs`, absent `checkJs`, exclusions, source identity,
diagnostics, scores and acceptance rules are unchanged. The exporter remains
byte-identical to published head `8adb197b4320b6ef315e39c620282270d394c06e`.
Unexpected tracked mutations still fail. Owned tests verify each observed edit,
the pair, unrelated source mutation rejection, and clean explicitly committed
configuration. The configuration regression failed before the edit (1 failed,
5 passed, 0 skipped); these are guard tests with a synthetic compiler response,
not a real application build. Fresh automatic hosted CI must test the candidate
against Next's actual generation behavior.

Candidate validation: **96 passed, 0 failed, 0 skipped** in 54.44 seconds across
exporter/importer, GitHub adapter, owned source-guard and existing CI-evidence
suites. One pre-existing escape-sequence warning remains. Separate read-only
review found no blocker in the exact configuration adjustment or the portable-test
fix. Final logs: `/tmp/nico-ci-config-red.txt` and
`/tmp/nico-ci-config-final-green.txt`. No local application build, dependency
download, manual workflow dispatch or production action was performed.

## Git object-ID compatibility declaration

Parent's independent triage identified the sole blocking B324 HIGH/HIGH finding
in Security Audit Evidence run 38667418455 at the Git blob SHA-1 calculation.
The reported verified artifact is 11943011434, 240,593 bytes, SHA-256
`1cd85fbecbb24f415eaba920902295d752d7ab71b06708588cfae77f4add4b30`.
Local targeted Bandit 1.9.4 reproduced that one finding with no scan errors.

The calculation now explicitly uses `usedforsecurity=False`: it computes Git's
canonical `blob <length>\0<bytes>` object ID for protocol compatibility. This flag
does not strengthen SHA-1. Independent SHA-256 archive authentication, provider
source hashes, retained inventory equality and reviewed-file hashes remain the
content integrity checks. Git-ID, metadata length and decoded-length mismatches
still fail. No scanner suppression, rule exception, score or acceptance gate was
changed.

Added controls compare the result with `git hash-object`, require the explicit
compatibility flag, reject incorrect IDs/lengths, and demonstrate that changed
content with a valid Git ID still fails retained SHA-256 inventory equality.
Existing modified-content, archive-digest and unreviewed-file controls remain.
The new tests recorded 1 failure and 4 passes before the declaration; targeted
Bandit after the correction reports **0 findings, 0 errors**. Separate read-only
review confirmed the independent SHA-256 binding and found no blocker.

Final focused validation: **101 passed, 0 failed, 0 skipped** in 58.15 seconds;
one pre-existing escape-sequence warning. `git diff --check` passed. Evidence logs:
`/tmp/nico-ci-git-sha1-red.txt`, `/tmp/nico-ci-git-sha1-green.txt`,
`/tmp/nico-ci-git-sha1-bandit-red.json`, and
`/tmp/nico-ci-git-sha1-bandit-green.json`. Existing trusted tooling only; no local
build, dependency installation, artifact retry or manual workflow dispatch.
