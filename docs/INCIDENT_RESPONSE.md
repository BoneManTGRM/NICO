# NICO Operational Incident Response

## Purpose

This runbook defines how NICO production incidents are detected, classified, contained, investigated, recovered, and closed. It applies to the hosted frontend, backend API, scanners, assessment workflows, report generation, human review, approval, delivery, persistence, and deployment controls.

Operational telemetry supports investigation. It does not authorize score changes, remediation, production deployment, or client delivery.

## Ownership

The active NICO production operator owns initial triage and containment. The repository owner owns release and rollback decisions. A human reviewer owns report approval and client-delivery decisions. Security-impacting incidents require explicit human review before service restoration.

Do not delegate production-impacting actions to autonomous code without an approved change, test evidence, rollback plan, and recorded operator decision.

## Correlation and evidence

Every production response carries `X-NICO-Correlation-ID`. Use that identifier to connect frontend reports, API requests, scanner runs, report generation, approvals, and delivery events.

Operational event records may contain only:

- correlation ID;
- route template and method;
- status code, duration, outcome, and severity;
- recognized run, scan, report, approval, access, receipt, evidence, job, and export identifiers;
- bounded timestamps and safe deployment/storage state.

Do not place request or response bodies, query values, cookies, authorization headers, admin tokens, API keys, credentials, provider response bodies, source snippets, or raw exception messages in incident records.

Preserve the release manifest, exact commit SHA, relevant correlation IDs, event IDs, scanner/report/approval identities, and the last-known-good deployment record. Do not edit failed evidence into a passing state.

## Severity levels

### P0 — critical integrity or security incident

Examples:

- confirmed secret or credential exposure;
- cross-customer data disclosure;
- unauthorized client delivery;
- destructive production action;
- approval, receipt, or artifact-integrity bypass;
- confirmed malicious compromise.

Required response:

1. Stop affected writes and delivery immediately.
2. Activate the kill switch or disable the affected route/service when available.
3. Preserve evidence before making repairs.
4. Revoke affected delivery links or credentials through an approved human action.
5. Notify the repository owner and designated security owner immediately.
6. Do not restore service until the root cause, blast radius, repair, and verification are reviewed.

### P1 — production outage or durable integrity failure

Examples:

- repeated unhandled server failures;
- production API unavailable;
- durable Postgres corruption or unavailable required records;
- frontend/backend release mismatch;
- release identity or last-known-good verification failure;
- lost or inconsistent approval/delivery state.

Required response:

1. Assign an operator immediately.
2. Block new trusted assessment or delivery work when integrity is uncertain.
3. Identify the failing release SHA and correlation IDs.
4. Compare against the last-known-good deployment record.
5. Roll back only through a normal tracked revert and the complete production release gate.
6. Verify storage, readiness, assessment, report, approval, and delivery boundaries before reopening.

### P2 — degraded production service

Examples:

- scanner/provider unavailable;
- request timeout or elevated timeout rate;
- readiness blocked or degraded;
- queue age or failure rate above the operating threshold;
- report generation materially delayed;
- event pipeline write/read failures;
- non-durable memory fallback active in hosted production.

Required response:

1. Investigate promptly using `/operations/observability` and relevant correlation IDs.
2. Keep missing or failed evidence labeled unavailable.
3. Do not describe degraded scanner or provider state as clean evidence.
4. Reduce intake or pause expensive workflows when queue growth threatens reliability.
5. Escalate to P1 if data integrity, sustained outage, or client delivery is affected.

### P3 — isolated bounded workflow error

Examples:

- invalid client input;
- rejected authorization or admin token;
- one failed evidence upload;
- one recoverable assessment transition;
- expected policy block.

Required response:

1. Confirm the error is isolated and bounded.
2. Provide the correlation ID and safe recovery action.
3. Track recurrence; escalate to P2 when the same error becomes systemic.

### Info — expected operational activity

Successful requests and expected policy outcomes are retained for correlation and trend analysis. Informational events are not incidents by themselves.

## Detection and triage

1. Confirm the exact production frontend and backend origins.
2. Capture the correlation ID from the response or operator report.
3. Review `/operations/observability` with operator authentication.
4. Filter `/operations/events` by correlation ID or severity.
5. Verify `/operations/readiness` and the deployed commit identity.
6. Check Vercel, Railway, and required GitHub Actions for the same exact SHA.
7. Identify affected customer/project/run identifiers without copying private payloads into the incident record.
8. Assign severity based on impact and integrity, not cosmetic appearance.

## Containment

Use the least destructive action that stops further harm:

- pause new assessment intake;
- block client delivery;
- revoke a specific access grant;
- disable a failing provider integration;
- reduce scanner concurrency;
- switch an affected workflow to explicit human review;
- roll back through a tracked revert and production release gate.

Do not delete evidence, rewrite saved runs, suppress failed checks, mark unavailable scanners clean, or bypass approval to make the dashboard green.

## Recovery

Recovery requires evidence that the original failure is fixed and the operating boundary is intact.

Minimum recovery verification:

1. Required CI and security workflows pass for the exact recovery SHA.
2. Vercel and Railway report successful deployment for the same SHA.
3. The production release gate passes and records the release.
4. `/operations/readiness` reports the required semantic state.
5. Durable storage is active and required records survive restart where applicable.
6. Required scanners execute or truthfully block the workflow.
7. A fresh acceptance run verifies the affected path.
8. Report, review, approval, and controlled-delivery identities remain hash-bound.

A URL returning HTTP 200 is not sufficient recovery evidence.

## Rollback

1. Identify the latest successful last-known-good GitHub production deployment.
2. Verify its release SHA and release-identity hash against the retained manifest.
3. Create and merge a normal revert so current `main` represents the intended rollback state.
4. Redeploy both Vercel and Railway from that exact current `main` SHA.
5. Run the complete Production Release Gate again.
6. Perform a fresh Mid or Full acceptance run before resuming client delivery.

Never operate a newer frontend with an older backend, or an older frontend with a newer backend, and call the combination ready.

## Closure and follow-up

An incident may close only when:

- severity and impact are documented;
- the root cause is supported by evidence;
- containment and recovery actions are recorded;
- the exact repair/revert SHA is known;
- verification results are attached;
- any affected client delivery is reviewed by a human;
- follow-up defects have owners and acceptance criteria;
- sensitive values were not copied into issue comments, logs, or artifacts.

For P0 and P1 incidents, add a post-incident review covering detection gap, response time, blast radius, repair, verification, rollback readiness, and prevention work.

## Retention and redaction

Retain operational event evidence according to the hosted storage policy and applicable customer agreement. Production events must use durable Postgres. Memory fallback is diagnostic only and must remain labeled non-durable.

Keep event reads bounded. Retain only safe provider origins rather than full provider URLs. Never retain raw credentials, tokens, cookies, request bodies, query values, exception messages, source snippets, or private provider responses.
