# NICO Operations Readiness

NICO distinguishes **liveness** from **operational readiness**.

- `/health` confirms the API process is reachable and can return a basic response.
- `/operations/readiness` evaluates whether the hosted system has the minimum semantic controls required for trusted operation.

A reachable service may still be operationally blocked.

## Readiness states

- `ready`: every required operational check passed.
- `degraded`: required controls passed, but one or more advisory checks need attention.
- `blocked`: one or more required controls failed or could not be verified.

## Required checks

The readiness contract evaluates:

1. Deployed commit identity is available.
2. Deployed commit matches the expected build marker when a hard-pinned marker exists.
3. Report truth guard is active.
4. Hosted storage is durable.
5. Scanner execution is enabled.
6. Runtime configuration loaded successfully.
7. Required workflow routes are registered.

Advisory checks include operator admin-write configuration and GitHub metadata confidence. Advisory failures do not create a false ready state; they produce a degraded state and remain visible.

## Terminal check

After every production deployment or environment change, run:

```bash
python scripts/check_operations_readiness.py https://YOUR-NICO-API-HOST
```

The command exits:

- `0` when the readiness endpoint reports `ready`;
- `1` when it reports `degraded` or `blocked`;
- `2` when the base URL is missing or invalid.

Use `--allow-degraded` only for an explicitly approved diagnostic window:

```bash
python scripts/check_operations_readiness.py https://YOUR-NICO-API-HOST --allow-degraded
```

This does not authorize client delivery and does not override evidence or human-review gates.

## Deployment gate

Do not treat a deployment as operationally complete until all of the following are true:

- NICO CI passes.
- Node.js CI passes.
- CodeQL passes.
- Audit Evidence passes.
- Security Audit Evidence passes.
- Vercel deployment succeeds.
- Railway deployment succeeds.
- `/operations/readiness` reports `ready`.
- A post-deployment smoke check passes.

## Failure handling

When readiness is blocked:

1. Read `blockers` and the failed check records.
2. Fix the underlying environment, deployment, storage, truth-guard, scanner, or route defect.
3. Redeploy if the deployed commit or runtime code is stale.
4. Re-run the readiness checker.
5. Do not generate or deliver a client-facing report from a blocked deployment.

Readiness success proves operational prerequisites only. It does not prove a repository is clean, a scanner finding is resolved, or a report is approved for delivery.
