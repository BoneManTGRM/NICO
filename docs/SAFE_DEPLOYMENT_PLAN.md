# NICO Safe Deployment Plan

This document is a planning artifact only. It does not deploy NICO and does not add cloud configuration, production credentials, hosted login, billing, live connector execution, or live external scanning.

## Deployment gate

NICO must remain local-first until these controls are implemented, reviewed, tested, and explicitly approved:

- authentication
- RBAC
- tenant isolation
- server-side private-value storage
- audit logs
- approval workflows
- billing readiness
- connector permissions
- backend API gateway
- no exposed API keys
- no live external scanning until explicitly approved
- staged rollout
- threat model
- rollback plan

## Authentication

Future hosted NICO should require identity before any workspace, report, connector, or tenant-scoped data is accessible. Local preview and static GitHub Pages must not imply hosted authentication exists.

## RBAC

Roles should follow least privilege. Initial role set: owner, admin, analyst, developer, viewer. Sensitive actions require explicit approval even when the role has broad privileges.

## Tenant isolation

Tenant-scoped data must never cross tenant boundaries. This includes scans, findings, reports, repair memory, audit logs, connector settings, usage records, and billing records.

## Private-value storage

Future hosted NICO must use server-side protected storage. Static preview files, browser storage, frontend bundles, reports, and logs must never contain raw private values. Current repository work is placeholder-only and does not claim production-grade encryption.

## Audit logs

Every sensitive action should write an audit event with actor, tenant, action, timestamp, risk level, approval requirement, and masked details.

## Approval workflows

Human approval is required before production mutation, dependency upgrade, external connector access, report export, private-value usage, repo setting changes, hosted SaaS behavior, or high-risk swarm actions.

## Billing readiness

Billing must be added only after authentication, tenant isolation, audit logging, and private-value controls are ready. Billing logic must not expose API keys or connector credentials.

## Connector permissions

Connectors remain disabled by default until reviewed. Connector policies must define allowed scopes, blocked operations, required role, required approval level, private-value reference rules, and audit requirements.

## Backend API gateway

A hosted backend should centralize API access, authorization, tenant scoping, audit enforcement, rate limits, and approval checks. Frontends must not call third-party APIs directly with exposed keys.

## Live external scanning

Live external scanning is disabled until explicitly approved and scoped. Hosted NICO must only scan authorized assets, with documented authorization and safe rate limits.

## Staged rollout

1. Local-only validation.
2. Private hosted alpha with demo data only.
3. Single-tenant pilot with authorization controls.
4. Multi-tenant beta after tenant isolation review.
5. Production launch only after security review, monitoring, rollback, and incident process.

## Threat model

The hosted design must address prompt injection, over-broad agent permissions, private-value exposure, cross-tenant access, unsafe connector permissions, report leakage, dependency risk, and unauthorized scanning risk.

## Rollback plan

Every hosted release must have a rollback path, disabled-by-default risky features, database backup strategy, connector kill switch, audit preservation, and clear operator approval steps.

## Current status

This plan is documentation only. NICO remains defensive-only, local-first, and not production SaaS.
