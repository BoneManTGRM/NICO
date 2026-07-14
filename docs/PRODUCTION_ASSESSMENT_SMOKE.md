# Authorized Production Assessment Smoke

This workflow is a controlled production proof mechanism. It is not a general-purpose assessment launcher and does not mark the production-proof roadmap item complete until a passing combined artifact is retained and reviewed.

## Required GitHub environment

Create a protected GitHub Actions environment named `production-smoke`. Configure required reviewers where available, then add:

Repository or environment variables:

- `NICO_PRODUCTION_FRONTEND_URL`: the HTTPS frontend origin, without a path, query, credentials, or fragment.
- `NICO_PRODUCTION_BACKEND_URL`: the HTTPS backend origin, without a path, query, credentials, or fragment.
- `NICO_PRODUCTION_SMOKE_REPOSITORY`: the single owner/name demonstration repository explicitly authorized for this proof.
- `NICO_PRODUCTION_SMOKE_ALLOWED_HOSTS`: comma-separated bare hostnames for the configured frontend and backend only.
- `NICO_PRODUCTION_BACKEND_STATUS_CONTEXT`: the exact successful GitHub deployment-status context for the production backend.

Environment secret:

- `NICO_PRODUCTION_SMOKE_ADMIN_TOKEN`: the production admin token. Never place this value in a workflow input, repository variable, issue, pull request, artifact, log, browser form, screenshot, or chat.

## Operator gate

Run **Authorized Production Assessment Smoke** manually from `main`. Supply the exact deployed commit, an internal authorization reference, and select `I_CONFIRM_AUTHORIZED_PRODUCTION_SMOKE`.

The workflow fails closed when the selected ref or exact commit differs, authorization is not explicitly confirmed, a URL is not HTTPS, a URL contains credentials or query data, the repository differs from the allowlist, a host is not allowlisted, a deployment status is not successful, or the secret is missing.

## Execution boundary

The runner first verifies the exact frontend/backend deployment statuses, the deployed assessment page, and backend health. No assessment starts when preflight fails.

After preflight, pinned Playwright Python `1.61.0` opens the real deployed assessment page and performs the normal authorized UI flow for Express, Mid, and Full. The browser UI creates the only start request for each tier. The evidence finalizer does not issue separate API starts and never retries a start.

For each tier, the runner:

- opens the exact deployed `/assessment?tier=<tier>#assessment` route;
- fills the allowlisted repository and one isolated production-smoke client/project scope;
- selects the explicit authorization checkbox;
- clicks the tier Run button exactly once;
- captures the corresponding backend start response and all Mid/Full continuation responses;
- verifies Mid and Full poll only the status URL containing the exact returned run ID;
- compares the visible browser run ID with the final network response identity;
- verifies report identity, review-request identity where required, human-review status, and `client_ready: false`;
- rejects unexpected assessment API origins, duplicate starts, changed run identities, failed/unavailable terminal evidence, missing screenshots, or missing identities;
- retains one full-page screenshot and its SHA-256 for each tier.

The synchronous Express browser flow is allowed up to 900 seconds. General deployment and health requests remain bounded to 60 seconds, while Mid and Full remain bounded by the deployed UI&apos;s exact-run continuation ceiling. The complete protected job remains limited to 60 minutes.

The retained artifact package includes:

- deployment and health preflight JSON;
- bounded browser/network evidence JSON;
- the canonical combined JSON and Markdown proof;
- Express, Mid, and Full screenshots;
- no full response bodies, credentials, database URLs, provider secrets, approval authority, or delivery authority.

## Safety and truth boundaries

The workflow does not approve reports, create delivery access, redeem delivery links, apply repairs, open pull requests, modify production code, or claim that all defects are absent. It deliberately does not issue a second start request as a destructive duplicate probe. A timed-out, blocked, missing, changed-identity, unexpected-origin, or unavailable result remains failed evidence.

A passing combined artifact proves only the bounded behavior recorded for the exact deployed commit and authorized repository. Human review of the retained package remains required before the final roadmap item can be marked complete.
