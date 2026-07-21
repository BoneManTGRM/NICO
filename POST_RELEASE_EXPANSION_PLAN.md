# NICO post-release expansion program

Status: active follow-up to the production-accepted Express + Comprehensive release.

Accepted production baseline: `59a0fd3ae20fcb5a8c4321ea5fc2de833a73eb04`.
Tracking issue: #529.

## Rules

1. Preserve the accepted Express and Comprehensive production behavior.
2. Missing provider, storage, performance, accessibility, approval, or verification evidence fails closed.
3. Every implementation PR must use an exact head SHA, pass all required workflows, and retain evidence.
4. Live-provider claims require live representative accounts; normalized fixtures alone are insufficient.
5. No raw credential may be committed, logged, serialized, returned by an API, or embedded in an artifact.
6. Monitor + Execute may propose repairs automatically, but production-impacting execution always requires explicit scoped human approval.
7. Client delivery remains separately human-reviewed and auditable.

## Release-quality work packages

### Provider platform

- [ ] P1 — Credential references, redaction, host allowlists, expiry, and rotation metadata.
- [ ] P2 — GitLab.com and self-managed GitLab read-only API client.
- [ ] P3 — Bitbucket Cloud read-only API client.
- [ ] P4 — Bitbucket Data Center/Server read-only API client.
- [ ] P5 — Azure DevOps Repos, Pipelines, and Boards read-only API client.
- [ ] P6 — Complete pagination, bounded retry/backoff, rate-limit, outage, and partial-access truth.
- [ ] P7 — Verified GitLab, Bitbucket, and Azure webhook/poll synchronization with replay protection.
- [ ] P8 — Live representative provider acceptance and canonical evidence equivalence.

### Infrastructure and operational proof

- [ ] I1 — Select and document the supported production durability contract: Railway Postgres or approved durable Railway-volume storage.
- [ ] I2 — Automated backup and restore proof tied to exact run identity and integrity hash.
- [ ] I3 — Storage, queue, provider, report, and delivery observability plus actionable alerting.
- [ ] I4 — Tested rollback and disaster-recovery evidence retained with the release.

### Extended hardening

- [ ] H1 — Large-repository performance and bounded-resource acceptance.
- [ ] H2 — Large-evidence-packet performance and artifact-size acceptance.
- [ ] H3 — Clean, vulnerable, partial-access, timeout, outage, revoked-approval, and interrupted-run matrix.
- [ ] H4 — Keyboard, screen-reader, contrast, reduced-motion, focus, semantic-heading, long-string, and pseudo-localization acceptance.
- [ ] H5 — Two consecutive production-equivalent performance/accessibility passes on the same immutable SHA.

### Monitor + Execute

- [ ] M1 — Recurring repository and delivery-state monitoring with stable identity and change detection.
- [ ] M2 — Evidence-bound alerting, deduplication, ownership, severity, and escalation rules.
- [ ] M3 — Smallest-reversible remediation proposals with verification and rollback plans.
- [ ] M4 — Explicit scoped approval records with expiry, revocation, and immutable audit identity.
- [ ] M5 — Sandboxed execution adapters that cannot operate outside proposal and approval scope.
- [ ] M6 — Exact-SHA post-execution verification, residual-risk recording, rollback, and auditable closure.
- [ ] M7 — Production acceptance proving no execution occurs without approval and no unverified repair closes automatically.

## Foundation implemented in the first follow-up PR

- Credential references and secret-redaction boundary.
- Concrete initial GitLab, Bitbucket Cloud, and Azure DevOps read-only clients.
- Bounded retry, rate-limit, pagination, HTTPS, and host-allowlist enforcement.
- Provider webhook signature and replay-verification primitives.
- Machine-testable extended hardening matrix.
- Approval-gated Monitor + Execute state contract.

The foundation is not a claim of live-provider, backup/restore, production accessibility, performance, or execution acceptance. Those claims remain blocked until their exact work packages pass against representative production-equivalent systems.

## Completion gate

Issue #529 may close only when all retained work packages pass or are moved into separately approved trackers without losing their acceptance criteria, evidence links, or safety boundaries.
