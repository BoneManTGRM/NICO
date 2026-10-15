# Trusted TypeScript local prototype — 2026-10-15

Base: 86e66391af6cacb28af467d6bf35a768f0f00046 (live main checked before work).
Branch: prototype/trusted-typescript-offline. No production integration,
flag changes, score changes, deployment, assessments or downloads. This document
records the initial local prototype; the subsequent dormant draft scope is in
OFFLINE-BUNDLE-AND-ISOLATION.md. Draft publication grants no execution authority.

## Implemented boundary

The standalone compiler module loads the already installed TypeScript 6.0.3
compiler bytes only after comparing controller-supplied SHA-256 trust anchors for
its package, compiler and complete library inventory. No package resolution from
target source occurs. Native Node is identified separately. Test anchors establish
identity of the provisioned local tools; they do not prove supply-chain provenance.

Inputs are a digest-bound manifest with exact repository/commit/run/snapshot
identity and per-file bytes/hashes. The controller independently checks the expected
identity. CompilerHost reads only a virtual immutable map of source/config/library
text; it never falls back to ts.sys. It constructs a real Program and obtains all
pre-emit diagnostics, including semantic cross-file diagnostics and related
information. Source content is never executed. Emission and incremental writes are
disabled. Receipts bind effective options, root/read populations, input/diagnostic
hashes, compiler identity and results. Native bounded output is retained unchanged.

Dependency/generated entries, project references/extends, plugins, unchecked JS,
skipped library checks and unknown closure are deliberately unsupported and
incomplete. Missing declarations are not stubbed or ignored. Nonliteral imports
are incomplete. This restricted prototype cannot yet check NICO's Next project.
Standard source-level TypeScript directives retain compiler semantics; no claim
of application correctness or exhaustive runtime dependency discovery is made.

Limits: 256 manifest files, 2 MiB aggregate source/config, 16 MiB trusted libraries;
controller input 4 MiB, stdout 8 MiB, stderr 32 KiB, wall deadline 15 seconds,
Node heap 256 MiB. Controller limits can only be reduced within fixed maxima.
Process groups are killed on timeout/output failure; no receipt receives success
credit after incomplete capture. The heap limit is NOT a total RSS/address-space
limit. No hard CPU/cgroup/PID qualification is claimed.

Every receipt explicitly says os_isolation_verified=false and
qualified_for_production=false. The API is for owned synthetic fixtures only.
A CompilerHost and scrubbed environment are NOT OS isolation.

## Required before any production integration

A separate TypeScript worker boundary must be authorized and demonstrated. The
existing dedicated worker container source has network=none, read-only root,
non-root uid/gid, dropped capabilities, no-new-privileges, cgroup CPU/memory/PID
bounds, private bounded temporary storage, no controller credentials/socket,
inside-container assertions, output/deadline controls and forced cleanup. It is
an existing tool-specific facility, NOT current TypeScript qualification. It was
only inspected; no container/workflow/profile was changed or run.

A TypeScript profile must independently verify these controls, use an immutable
image and fixed entry point, read no host assessed checkout or secrets, accept
only controller-frozen inputs, bound disk/FD/process/CPU/RSS/output/wall resources,
and prove process cleanup on cancellation and failures. Resource values need
qualification for TypeScript rather than reuse of another tool's budget.

The future offline bundle verifier must establish:

- Exact lockfile bytes/hash tied to the assessed commit; exact package locations,
  versions and resolved identities, verified archive integrity from the lockfile,
  and a digest manifest of extracted data with no traversal/symlink escapes.
- Compiler and standard-library identities tied to the approved image, separate
  from dependency versions. Never execute dependency JavaScript or package scripts.
- Generated declaration hashes bound to the same source SHA, lockfile, generator
  identity/config and an authorized build's immutable provenance. No stubs or
  omitted .next inputs. Unknown/mismatched/stale evidence stays incomplete.
- Verification of signatures/attestations by an independent controller trust
  root, not trust in a target-provided digest or self-declared successful build.

Existing workflow definitions can identify retained outputs without starting a
build: node.js.yml uploads audit-results only; the frontend production proof
uploads release-proof JSON; phase9-production-report-and-node-scanners uploads
scanner logs/manifest; frozen-sha-scanner-proof uploads raw scanner/report proof.
These may supply exact-revision execution/provenance evidence if an authorized,
retained artifact is independently verified. The inspected definitions do not
establish a complete retained dependency/generated-declaration bundle. No artifact
was fetched, and no current artifact existence, contents or expiry is claimed.
The blocked diagnostic/report was not accessed through another route.

## Validation

Baseline before module existed: 20 failing owned-fixture regression cases.
Independent review reproduced three closure false-clean cases (skipLibCheck,
unchecked JS, nonliteral dynamic import) and two later gaps (missing compiler
library, incomplete-receipt validation). All have regression controls and fixes.
Final focused run: 64 passed in 33.10 seconds (42 prototype cases plus 22
existing TypeScript diagnostic, project-command policy and ledger-truth cases).
Independent read-only reviewer: all 42 prototype cases passed in 32.33 seconds;
no remaining blockers for owned-fixture-only use. Bytecode and pytest caching
were disabled. No real assessed repository was passed to the prototype.

Tests use the existing provisioned Node and TypeScript installation explicitly;
they do not install missing tools or qualify a different CI/production image.
The local red/green logs are /tmp/nico-typescript-prototype-red.txt and
/tmp/nico-typescript-prototype-final.txt. A baseline absence failure establishes
new functionality, not a claim that this prototype fixes a production score.

The next decision is whether to authorize the offline provenance verifier and a
separate TypeScript isolation profile. Do not wire this prototype into production
or promise a numeric score recovery before those prerequisites and exact-run
artifacts are verified. Existing scoring and approval/delivery gates are untouched.
