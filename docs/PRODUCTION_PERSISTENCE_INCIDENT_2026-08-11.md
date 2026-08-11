# Production persistence incident — 2026-08-11

## Scope

This incident record is limited to the exact production release `fdcea0838fe5047968f515533e9b84db1dc40126` and the production-persistence dependency that blocks further NICO Completion Program advancement.

## Observed production evidence

- Vercel exact-release deployment reached success.
- Railway NICO initially reported success and later reported deployment failure for the same exact release.
- Exact-main iOS WebKit Paint Proof failed because the browser never received and persisted a Comprehensive run ID within the bounded acceptance window.
- Exact-main Mobile Restart Production Proof failed at the same durable-run-identity boundary.
- Two-Service Production Acceptance failed because the required mobile/iOS production proofs did not pass.
- Railway operator notification evidence shows repeated NICO production deployment failures and a crashed Postgres deployment in the same production environment.
- The repository's `Postgres Restart Proof` is synthetic by design and explicitly does not claim live-production database health.

## Current dependency boundary

Phase 2 work does not advance while exact-main production persistence is unresolved. The first incomplete dependency is live production database/runtime availability.

The repository repair in this branch does not silently switch canonical stores. It converts database unavailability into a bounded fail-closed production state instead of allowing an import/startup crash or leaking provider/database detail. Existing canonical run identity, exact-SHA requirements, report semantics, human review, and blocked pre-approval client delivery remain unchanged.

## Operator dependency

Repository code cannot restart or repair the Railway Postgres service. The Railway Postgres deployment must be restored and its provider logs inspected through Railway. Once the database is healthy, the NICO service must deploy against the same canonical durable store and pass the normal exact-main production gates before completion authority can advance.

## Preserved boundaries

- one public product: NICO Comprehensive
- one client report
- no automatic cross-store fallback
- assessed repository remains read-only
- exact immutable commit verification remains required
- automation cannot create human disposition, risk acceptance, approval, or client-delivery authorization
- human review remains mandatory
- client delivery remains blocked before authorized approval
