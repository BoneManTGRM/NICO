# NICO Master Roadmap

## Current implementation pass — PR #1

Implemented in the repair-first foundation branch:

- stabilize MVP
- normalized findings
- RYE scoring
- TGRM repair candidates
- verification workflow
- repair memory
- owner/developer/reparodynamic/compliance reports
- focused UI improvements
- module foundation
- scanner availability detection
- validation and hardening documentation
- frontend TypeScript configuration hardening

Validation status:

- Backend CLI checks passed on a local equivalent checkout.
- API endpoint checks passed on a local equivalent checkout.
- Frontend lint, build, and dev startup passed after TypeScript target modernization and Next JSX config compatibility update.
- The exact remote branch still needs one final developer-machine or Codex checkout because this environment cannot resolve `github.com` for cloning.

## Required before merge

- keep PR #1 as a draft
- check out `upgrade/repair-first-foundation` directly
- rerun backend, API, and frontend checks
- add explicit no-raw-secret regression tests for reports/API responses
- confirm generated runtime files are not committed
- update the PR with exact-branch results

## Future Phase A — Cyber Twin

Graph tables, node/edge model, asset extraction, finding-to-asset linking, repair-to-finding linking, route/file/dependency relationships, API endpoint `GET /cyber-twin`, and cyber twin UI page.

## Future Phase B — AI Agent Security

Tool permission scanner, memory risk scanner, connector exposure scanner, prompt injection surface scanner, cross-user memory contamination checks, unsafe autonomous action detector, identity inventory, audit review, kill-switch verification, and least-privilege repair plans.

## Future Phase C — NICO-Bench Local

`python -m nico bench local`, vulnerable fixtures, benchmark report, and optional comparisons against external scanners when available.

## Future Phase D — Connectors

GitHub first, then Docker, Supabase/Firebase, Cloudflare, Stripe/Mercado Pago, Vercel/Render/Railway, PostgreSQL, identity, error logs, and workflow tools.

## Future Phase E — Production Hardening

Auth, RBAC, tenant isolation, encrypted secrets, sandboxing, rate limits, audit logs, signed webhooks, backup/restore, kill switch, approval workflows, and secure report permissions.

## Future Phase F — Security Regression Tests

Add tests proving fake raw secrets are never emitted in generated reports, API JSON responses, CLI output, or frontend fields.
