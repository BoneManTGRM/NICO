# Unified production release identity gate

## Root cause

Unified Production Acceptance waited for successful GitHub deployment status contexts, then immediately opened the production assessment page. A successful Vercel status can represent a completed deployment without proving that the `app.nicoaudit.com` production alias is already serving that exact commit. Workflow run `30201030003` therefore reached the browser against stale production HTML and observed the obsolete English action label `Run NICO Assessment` even though the checked-out source required `Create engagement and capture repository snapshot`.

## Repair

The unified acceptance workflow now verifies the actual production custom domain before browser execution. The gate:

- polls the uncached `/api/release` endpoint;
- requires the exact release SHA;
- requires UI contract `expert-engagement-v2`;
- requires deployment environment `production`;
- uses no-store headers and a unique cache-busting query;
- verifies the canonical workspace attributes;
- verifies the exact English and Spanish action labels;
- rejects preview deployments, stale aliases, obsolete copy and partial responses;
- writes an immutable diagnostic artifact for both passing and failing runs.

The existing report, immutable-run, human-review and blocked-delivery acceptance requirements remain unchanged.

## Operational interpretation

A green provider deployment status is necessary but not sufficient. Unified production acceptance starts repository processing only after the configured production origin proves that it serves the expected frontend release and UI contract.
