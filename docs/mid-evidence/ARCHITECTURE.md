# NICO Mid Evidence — Architecture Context

Status: version-controlled context for human review. This document describes intended structure and current repository boundaries; it is not proof that every deployed runtime path behaves correctly.

## System boundary

NICO is an authorized, defensive technical-assessment and repair-planning system. It does not authorize exploitation, authentication bypass, credential theft, destructive actions, or offensive automation.

## Major components

1. **Next.js operator interface** — `apps/web` contains the browser command center and the Mid review, report, approval, and delivery screens.
2. **FastAPI backend** — `nico.api.production:app` is the production backend entry point. It installs evidence, scoring, scanner, report, approval, and delivery policies before registering the complete Mid route surface.
3. **Snapshot-bound assessment orchestration** — each Mid run captures an exact repository commit and binds repository evidence, scanner execution, scoring, report generation, review, approval, and delivery to that run and snapshot identity.
4. **Scanner worker** — the isolated temporary checkout executes configured dependency, secrets, static-analysis, test, and build tools when available. Missing binaries, failures, and timeouts remain explicit evidence states.
5. **Truth and scoring layer** — technical conclusions use repository and scanner evidence. External product, build, stakeholder, and roadmap context remains human-review-bound and cannot change a score automatically.
6. **Report and governance layer** — Mid draft, approval, approved artifact, delivery grant, acknowledgement, and receipt are separate stages with hash-bound identities.
7. **Persistence layer** — storage adapters retain run, evidence, report, approval, delivery, receipt, and audit records. Production durability depends on the configured adapter and environment.

## Trust boundaries

- Repository code evidence is bound to the captured commit.
- Commit, pull-request, CI, and deployment history is time-window operational evidence rather than exact-commit code evidence.
- User-submitted or version-controlled product context is not automatically treated as proof of runtime behavior.
- Human review is required before approval and client delivery.
- Unsupported clean claims are prohibited.

## Human validation checklist

- Confirm the deployed frontend points to the intended backend.
- Confirm the backend is running `nico.api.production:app`.
- Confirm durable storage is configured for client delivery workflows.
- Confirm the Mid run snapshot SHA matches the intended repository state.
- Confirm scanner evidence and report hashes belong to the same run.
