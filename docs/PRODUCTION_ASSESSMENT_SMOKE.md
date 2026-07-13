# Authorized Production Assessment Smoke

This workflow is a controlled production proof mechanism. It is not a general-purpose assessment launcher and does not mark the production-proof roadmap item complete until a passing artifact and the required browser evidence are retained and reviewed.

## Required GitHub environment

Create a protected GitHub Actions environment named `production-smoke`. Configure required reviewers where available, then add:

Repository or environment variables:

- `NICO_PRODUCTION_FRONTEND_URL`: the HTTPS frontend origin, without a path, query, credentials, or fragment.
- `NICO_PRODUCTION_BACKEND_URL`: the HTTPS backend origin, without a path, query, credentials, or fragment.
- `NICO_PRODUCTION_SMOKE_REPOSITORY`: the single owner/name demonstration repository explicitly authorized for this proof.
- `NICO_PRODUCTION_SMOKE_ALLOWED_HOSTS`: comma-separated bare hostnames for the configured frontend and backend only.
- `NICO_PRODUCTION_BACKEND_STATUS_CONTEXT`: the exact successful GitHub deployment-status context for the production backend.

Environment secret:

- `NICO_PRODUCTION_SMOKE_ADMIN_TOKEN`: the production admin token. Never place this value in a workflow input, repository variable, issue, pull request, artifact, log, or chat.

## Operator gate

Run **Authorized Production Assessment Smoke** manually from `main`. Supply the exact deployed commit, an internal authorization reference, and select `I_CONFIRM_AUTHORIZED_PRODUCTION_SMOKE`.

The workflow fails closed when the selected ref or exact commit differs, authorization is not explicitly confirmed, a URL is not HTTPS, a URL contains credentials or query data, the repository differs from the allowlist, a host is not allowlisted, a deployment status is not successful, or the secret is missing.

## Execution boundary

The runner:

- verifies the exact commit has successful frontend and backend deployment statuses;
- verifies the deployed assessment page and backend health endpoint;
- sends exactly one start request for Express, Mid, and Full;
- polls only the exact Mid and Full run status URL returned by that tier;
- retains run, report, review-request, terminal-state, and unavailable-evidence summaries;
- requires explicit human-review and non-client-ready boundaries;
- writes bounded JSON and Markdown artifacts retained for 90 days.

It does not approve reports, create delivery access, redeem delivery links, apply repairs, open pull requests, modify production code, or claim that all defects are absent. It deliberately does not issue a second start request as a destructive duplicate probe. Duplicate-start protection and the visible browser state must be retained separately without creating an unintended second assessment.

## Roadmap interpretation

A passing workflow artifact is API and deployment evidence only. The roadmap remains incomplete until the matching production browser proof is retained, exact deployment identity is reconciled, and the combined evidence package is reviewed. Missing, blocked, failed, or timed-out evidence must remain explicit and cannot be converted into a passing claim.
