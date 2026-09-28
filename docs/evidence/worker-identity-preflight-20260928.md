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
