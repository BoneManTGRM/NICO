# Production worker identity diagnosis

The actual production Bitcoin intake `comprun_c4ebd22aefa7e768c162e9facf0bac8d`
selected `cpp-configure-first-v2` for Bitcoin commit
`05bc2f53ce0cb239c17dbdd6b261bd2db7d2a940`.

GitHub accepted dispatch of
`workerjob_3b2979a911b0fb07b0eb38983a043baaa74dc229a6e5b5a63726900661a1cbaf`
as [run 36417238573](https://github.com/BoneManTGRM/NICO/actions/runs/36417238573),
attempt 1, at NICO SHA `93aab53725315e0e9d9c1a1a5580c7b0403144ca`.
The consume job failed with `worker_http_rejected`. Backend HTTP logs establish
that the claim request received HTTP 401 at 2026-09-28T11:42:44Z. The durable job
remained queued, attempts 0, without a lease or receipt. No Bitcoin execution
or report completion is established.

Read-only production checks confirmed the expected release above, repository
`BoneManTGRM/NICO`, numeric repository ID `1282576027`, and successful GitHub JWKS
retrieval. GitHub's repository subject customization endpoint reported
`use_default: true`. These checks do not establish which signed claim failed.

The main-only assessment workflow now verifies its signed identity locally before
claiming. It invokes the existing worker verifier without modifying its predicates.
Diagnostic output contains only fixed error categories and boolean check results;
tokens, nonce values, claim values, and exception messages are never printed.
It cannot create a job, reset a job budget, call a backend, or mint operator access.
Workflow permissions, main-only selection, and the job-ID-only input are unchanged.

This is diagnostic instrumentation, not a claimed fix of the production rejection.
The next actual result must identify the rejecting predicate before changing any
authentication behavior. Repository/ref/workflow/release/audience/signature/lifetime
restrictions and human review/client delivery approval remain mandatory.

## Signed production diagnostic and bounded correction

PR #1651 merged as `9eda18ee330d7f9b2e4b0b5afaf4d986afad3bab` after
all 17 PR workflows and the push CI passed (48 successful checks, four
intentional production-only skips). Diagnostic run
[36419850732](https://github.com/BoneManTGRM/NICO/actions/runs/36419850732),
job `108919674220`, used the all-zero syntactically valid worker ID, confirmed
absent from production storage before dispatch. It did not create an assessment.

At 2026-09-28T12:08:22Z, signature verification succeeded and every boolean
identity predicate passed except `no_reusable_workflow`. The unchanged verifier
returned `worker_authority_mismatch`; the backend consume step was skipped.
This establishes that rejecting any nonempty `job_workflow_ref` blocks the
actual direct main workflow. No raw claim values or token were emitted.

The correction allows that optional identity pair only when BOTH
`job_workflow_ref` equals the already-required dedicated main workflow and
`job_workflow_sha` equals the exact expected release. If either claim is
present, both must be correct. Missing pairs retain compatibility; partial,
null, wrong-file, wrong-ref, wrong-repository and wrong-release pairs fail.
All signature, repository-ID, audience, caller workflow, main ref, lifetime,
runner and environment constraints remain enforced.

The preflight now separately reports safe boolean matches for the job workflow
reference and SHA. A fresh main diagnostic must verify the real pair before
production activation on the corrected release. Its values were not established
by the first diagnostic, so successful production authentication is not yet
claimed. The existing Bitcoin assessment is preserved without retries or resets.

Validation: 120 tests passed across authentication, preflight, HTTP boundary and
launcher suites, including exact self-identity acceptance and adversarial pairs.
