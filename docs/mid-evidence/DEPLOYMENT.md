# NICO Mid Evidence — Deployment Context

Status: version-controlled deployment context for human review. Configuration files show intended deployment behavior; live service health must still be verified separately.

## Hosted split

- **Frontend:** Next.js application under `apps/web`, suitable for Vercel or another Node-compatible host.
- **Backend:** FastAPI application started from `nico.api.production:app`, suitable for Railway or another Python web-service host.
- **Frontend-to-backend connection:** `NEXT_PUBLIC_NICO_API_URL` identifies the backend base URL.
- **Backend CORS:** the backend must allow only the intended frontend origins through its configured CORS policy.

## Backend container evidence

The repository Dockerfile:

- uses Python 3.11 slim;
- installs Git, Node.js, npm, and archive tools;
- installs Python requirements and optional Python scanners;
- attempts to install OSV-Scanner, Gitleaks, and TruffleHog binaries;
- installs global ESLint and TypeScript when available;
- starts Uvicorn with `nico.api.production:app` on the assigned port.

Optional scanner installation is intentionally non-strict. A successful container build does not prove that every scanner binary installed. Each fresh Mid run must report the actual tool state as completed, unavailable, failed, or timed out.

## Required validation after deployment

1. Confirm frontend and backend deployments are green.
2. Confirm the backend health endpoint responds from the configured public URL.
3. Confirm `/scanner-runtime` reports the deployed tool inventory.
4. Start a fresh Mid run after any scanner, scoring, or report change.
5. Confirm the run uses the expected snapshot commit.
6. Confirm OSV-Scanner is completed or explicitly unavailable with a reason.
7. Confirm Gitleaks and TruffleHog history status is explicit.
8. Confirm Bandit and Semgrep findings have material, review-only, or test-only dispositions.
9. Confirm the Mid draft and approval request bind to the same run and hashes.

## Non-claims

This document does not claim uptime, penetration resistance, scanner completeness, successful durable persistence, or client-readiness. Those conclusions require current runtime evidence and human review.
