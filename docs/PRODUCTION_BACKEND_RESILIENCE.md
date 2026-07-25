# Production Backend Resilience

## Problem addressed

The public assessment workspace can be deployed separately from the NICO assessment backend. A cold-started, restarting, temporarily unavailable, or incorrectly prioritized backend endpoint previously caused the frontend to stop immediately with `assessment_backend_unreachable`, even when an assessment run had already been created and completed stages were safely persisted.

## Proxy behavior

The bounded `/api/nico` proxy now:

- accepts deployment configuration from `NICO_API_URL`, `NICO_BACKEND_URL`, and the compatibility value `NEXT_PUBLIC_NICO_API_URL`;
- rejects credentials embedded in backend URLs;
- requires HTTPS in production;
- preserves the existing explicit route allowlist;
- retries transient HTTP states `408`, `425`, `429`, `500`, `502`, `503`, and `504`;
- retries network failures and bounded request timeouts;
- allows up to 240 seconds for assessment lifecycle requests;
- emits a request ID and proxy-attempt count;
- returns structured, retryable failure metadata without exposing the backend hostname or credentials.

Retries are bounded. They do not create access to arbitrary upstream routes and do not bypass authorization.

## Frontend behavior

The assessment workspace now:

- retries transient intake and continuation requests;
- retains the immutable run ID and completed stage evidence when a continuation request is interrupted;
- attempts a read-only run-status recovery before declaring failure;
- resumes from the recovered state instead of creating a duplicate assessment;
- gives the operator an actionable failure message when the backend remains unavailable.

## Deployment configuration

At least one of the following must contain the externally reachable HTTPS backend origin:

```text
NICO_API_URL=https://<backend-host>/
NICO_BACKEND_URL=https://<backend-host>/
NEXT_PUBLIC_NICO_API_URL=https://<backend-host>/
```

`NICO_API_URL` remains the preferred production setting. The other variables are bounded compatibility fallbacks, not browser-side direct access.

The backend must expose the Comprehensive production bootstrap and allow the frontend deployment to reach its public origin.

## Failure semantics

A permanently unavailable or misconfigured backend still fails closed. NICO does not fabricate assessment progress, scores, reports, or scanner completion. Previously completed stages remain associated with the displayed run identity and may be recovered after the backend becomes healthy.
