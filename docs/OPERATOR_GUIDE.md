# NICO Operator Guide

This is the canonical operating guide for authorized NICO assessments. It describes the current workflow and the meaning of system states. Historical patch notes and compatibility modules do not override this guide.

## Product boundary

NICO has one customer-facing assessment product and one client report: **NICO Comprehensive Technical Assessment**.

Historical Express, Mid, Deep, Full, Premium, Lite, Strategic, or other tier names are compatibility implementation details only. They are not customer choices, alternate assessment products, alternate scorecards, or alternate client reports. The normal customer start path is `/assessment` and it creates a Comprehensive engagement.

## Before an assessment

Confirm all of the following:

1. You own the repository or have explicit permission to assess it.
2. The repository is identified as `owner/repo` or a valid GitHub repository URL.
3. The hosted frontend has the canonical NICO backend URL configured.
4. The backend allows the frontend origin through `NICO_CORS_ORIGINS`.
5. Production storage and required secrets are configured for workflows that require durable state or admin actions.
6. The frontend and backend deployment identities match the intended release.
7. `/diagnostics/comprehensive-runtime` reports a ready, container-replacement-safe Comprehensive runtime before intake is created.

Never place GitHub tokens, NICO admin tokens, delivery tokens, API keys, or raw credentials into repository fields, client names, project names, report notes, URLs, or screenshots.

## Normal assessment workflow

Use the unified `/assessment` page.

1. Enter the authorized repository.
2. Optionally enter client and project names.
3. Confirm repository authorization.
4. Create the engagement and capture the immutable repository snapshot.
5. Preserve the returned exact run ID.
6. Leave the page open while automatic continuation is active, or recover the same exact run if the browser is interrupted.
7. Review the resulting evidence, unavailable notes, scores, and automated Comprehensive draft.
8. Use the protected review-by-exception workspace for authorized specialist dispositions and quality-control sampling.
9. Complete separate final human approval against the exact immutable report package.
10. Create client delivery only from the verified approved Comprehensive artifact.

Do not start a duplicate run merely because a scanner is still queued or running. Use the same run ID and Recovery when continuation is interrupted.

## State meanings

- **Complete**: the stage completed using the evidence described in the response.
- **Running / queued / pending**: work exists and is not terminal.
- **Unavailable**: required data, a binary, a manifest, a route, or a service could not be used. This is not a pass.
- **Failed / error**: attempted work failed. Review the stage message and correlation ID.
- **Blocked**: a safety, authorization, integrity, scope, persistence, or review gate prevented the action.
- **Human review required**: automated work reached its permitted boundary. This is expected for report approval and client delivery.
- **Not loaded**: the operator has not authenticated and loaded the evidence yet. This state is neutral.

## If a run appears stuck

1. Preserve the run ID.
2. Check whether the scanner or final-report stage is queued or running.
3. Use Recovery rather than starting a duplicate run.
4. Confirm frontend/backend release alignment.
5. Confirm `/diagnostics/comprehensive-runtime` is semantically ready.
6. Confirm the same canonical durable store is available; do not introduce an automatic cross-store fallback.
7. Inspect the correlation ID and operational events.
8. Check durable storage before assuming the run can survive a restart.
9. Rerun only after the existing run is terminal or explicitly unrecoverable.

A transient canonical Postgres outage is fail-closed. Readiness may re-probe the same durable store when recovery is explicitly supported, but it must never silently switch to SQLite, memory, or another database.

## If everything says unavailable

Treat widespread unavailability as an infrastructure or configuration incident until proven otherwise.

Check:

- backend deployment status
- frontend API URL
- CORS origin configuration
- deployment-commit alignment
- canonical Postgres configuration and persistence
- scanner-worker binary availability
- GitHub repository reachability
- authorization metadata
- operations readiness blockers

Do not lift scores or replace unavailable states with green placeholders. Restore the evidence path and rerun the affected stage.

## Human review by exception

NICO performs the repeatable technical analysis first. Authorized cybersecurity specialists primarily review genuine exceptions, ambiguous or material risks, changed evidence, grouped homogeneous work, and quality-control samples.

The protected reviewer workflow must preserve these distinctions:

1. raw scanner observation;
2. NICO automated technical triage;
3. authorized human disposition;
4. confirmed material finding;
5. final human approval; and
6. client-delivery authorization.

Technical triage does not create a human disposition. Human disposition does not create final approval. Final approval does not authorize delivery unless the exact delivery gates pass.

Reviewers must verify:

- repository, customer, project, run, scan, and report identities
- evidence provenance and collection times
- unavailable and failed evidence
- technical-triage recommendations and proof gaps
- grouped-review eligibility and underlying candidate IDs
- quality-control sample results
- score explanations and assurance state
- repair recommendations and verification steps
- residual risk and ownership where applicable
- report hashes and review-packet identity
- whether client delivery is actually allowed

Approval must be an explicit authorized human action. Requesting a review, completing technical triage, sampling candidates, or recording a human disposition is not final approval.

## Controlled delivery

Client delivery is allowed only when:

1. the reviewed automated draft is preserved;
2. required human dispositions and QC work are complete;
3. the final human decision is recorded;
4. a separate exact approved edition is generated;
5. artifact identities and hashes verify;
6. durable storage requirements are satisfied;
7. controlled access is created by an authorized operator; and
8. receipt or acknowledgment evidence is recorded when required.

The approved customer package contains one NICO Comprehensive client PDF. Revoke access when scope, recipient, expiration, or artifact identity is wrong.

## Deployment verification

After deployment or environment changes, run the hosted and operations readiness checks documented in the repository. HTTP 200 alone is insufficient. Verify the exact `main` SHA, Vercel deployment, Railway deployment, required Comprehensive routes, durable storage, scanners, truth gates, Mobile Restart, iOS WebKit, and Unified Production Acceptance.

## Evidence integrity rules

- Missing evidence is not passing evidence.
- A green CI check does not prove the production deployment contains the same commit.
- A scanner exit code is not automatically a severity rating.
- Scanner completion is not candidate approval.
- Automated technical triage is not human assurance.
- A report is not client-ready because a PDF exists.
- A score must explain its evidence and limitations.
- Candidate volume and reviewer workload are review metrics unless the canonical scoring contract explicitly says otherwise.
- Synthetic fixtures must be labeled synthetic.
- Live claims must be traceable to live evidence.

## Reviewer-effort measurement

The Phase 2 engineering target is approximately four combined cybersecurity-specialist hours for a normal supported repository with high automated-triage coverage and no major active incident or unresolved evidence conflict. This is an efficiency target, not a safety or approval gate.

Only real authorized specialist sessions may establish this metric. CI, fixtures, automation, or inferred timing must not fabricate the empirical result.

## Escalation record

For a failed or blocked production run, preserve:

- timestamp
- repository and authorized scope
- run ID and scan ID when created
- frontend and backend commit identities
- correlation ID
- failed stage or pre-intake blocker
- exact error or blocker
- persistence adapter and durability status
- corrective action
- verification result

This record is part of NICO's repair memory and should be sufficient for another operator to reproduce the failure without guessing.
