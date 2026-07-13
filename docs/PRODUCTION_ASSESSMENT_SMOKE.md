# Authorized production assessment smoke proof

The `Production Assessment Smoke` workflow is a manual, review-gated operator workflow for collecting bounded live evidence from the deployed unified assessment surface. Its existence does not complete the deployed Express/Mid/Full roadmap item. Completion requires a retained passing artifact from the exact deployed commit and a separate evidence review.

## Required GitHub environment

Create a GitHub Actions environment named `production-smoke`. Protect it with required reviewers and limit deployment branches to `main`.

Configure these environment values:

| Type | Name | Purpose |
|---|---|---|
| Secret | `NICO_PRODUCTION_SMOKE_ADMIN_TOKEN` | Production admin credential used only for the read-only Full delivery-readiness check. Never place it in a workflow input, issue, pull request, log, or chat. |
| Variable | `NICO_PRODUCTION_SMOKE_ALLOWLIST` | Comma- or newline-separated authorized demonstration repositories in exact `owner/name` form. |
| Variable | `NICO_PRODUCTION_SMOKE_FRONTEND_HOSTS` | Exact allowed frontend hostnames, without scheme or path. |
| Variable | `NICO_PRODUCTION_SMOKE_BACKEND_HOSTS` | Exact allowed backend hostnames, without scheme or path. |

A minimal current configuration would allow only the dedicated demonstration repository and the production frontend/backend hosts. Do not use a customer repository without retained explicit written authorization.

## Execution boundary

Run the workflow only from `main` after the exact commit has successful Vercel and Railway commit statuses. Supply:

- the HTTPS frontend and backend origins;
- the allowlisted repository;
- isolated customer and project identifiers;
- a non-secret written authorization reference; and
- the exact confirmation phrase `AUTHORIZED_PRODUCTION_SMOKE`.

The workflow then:

1. checks the deployed assessment page in a real headless browser without selecting the Run button;
2. proves the exact workflow commit has successful Vercel and Railway status contexts;
3. issues exactly one start request for Express, Mid, and Full;
4. follows only the retained Mid and Full run IDs through one exact status path per tier;
5. requires an evidence-bound draft/report, an explicit human-review boundary, and an explicit non-client-ready boundary;
6. uses the admin secret only on the read-only Full approved-delivery readiness endpoint and requires that human approval remains unsatisfied with no access grants, receipts, or acknowledgments;
7. records unavailable, failed, blocked, or timed-out evidence only as bounded status labels or hashes; and
8. uploads redacted JSON evidence for 90 days.

The workflow does not create or transition approvals, create delivery access, redeem or acknowledge delivery, request repairs, write configuration, or change production code. It does not retry start requests after an uncertain transport failure, because doing so could create a duplicate run. Redirects are rejected before the admin secret can be forwarded to another host.

## Reviewing the artifact

A passing artifact must report:

- `evidence_kind: authorized_live_production_smoke`;
- `live_claim: true`;
- `authorization_confirmed: true`;
- `status: passed`;
- one start per tier;
- exact Mid and Full run IDs and status paths;
- retained report and review-request IDs where the production tier returns them;
- `human_review_required: true` for every tier;
- `client_ready: false` for every tier;
- a blocked read-only Full delivery-readiness result with zero access, receipt, and acknowledgment activity;
- the exact frontend/backend commit; and
- successful Vercel and Railway deployment checks.

A failed or incomplete artifact is diagnostic evidence only. It must not be used to check off the production E2E roadmap item, approve a report, authorize delivery, or imply that unavailable evidence passed.
