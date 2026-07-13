# NICO Operator Guide

This is the canonical operating guide for authorized NICO assessments. It describes the current workflow and the meaning of system states. Historical patch notes do not override this guide.

## Before an assessment

Confirm all of the following:

1. You own the repository or have explicit permission to assess it.
2. The repository is identified as `owner/repo` or a valid GitHub repository URL.
3. The hosted frontend has `NEXT_PUBLIC_NICO_API_URL` configured.
4. The backend allows the frontend origin through `NICO_CORS_ORIGINS`.
5. Production storage and required secrets are configured for workflows that require durable state or admin actions.
6. The frontend and backend deployment identities match the intended release.

Never place GitHub tokens, NICO admin tokens, delivery tokens, API keys, or raw credentials into repository fields, client names, project names, report notes, URLs, or screenshots.

## Normal assessment workflow

Use the unified assessment page.

1. Select Express, Mid, or Full.
2. Enter the authorized repository.
3. Optionally enter client and project names.
4. Confirm authorization.
5. Select Run once.
6. Leave the page open while automatic continuation is active.
7. Record the returned run ID.
8. Review the resulting evidence, unavailable notes, scores, and draft report.
9. Complete human review through the appropriate advanced review surface.
10. Create client delivery only from a verified approved artifact.

Do not start a duplicate run merely because a scanner is still queued or running. Use the same run ID and Recovery when continuation is interrupted.

## Tier selection

### Express

Use Express for a fast evidence-bound baseline. It is appropriate when speed matters more than full evidence depth. Express output is still a draft and requires human review.

### Mid

Use Mid when exact-run repository and scanner evidence, a structured draft, and a review request are required. Mid continues automatically and stops at human review.

### Full

Use Full for the deepest configured assessment. Full continues through every available automated stage and stops at human review. A Full label does not guarantee that every optional scanner was available; inspect the evidence ledger and unavailable notes.

## State meanings

- **Complete**: the stage completed using the evidence described in the response.
- **Running / queued / pending**: work exists and is not terminal.
- **Unavailable**: required data, a binary, a manifest, a route, or a service could not be used. This is not a pass.
- **Failed / error**: attempted work failed. Review the stage message and correlation ID.
- **Blocked**: a safety, authorization, integrity, scope, or review gate prevented the action.
- **Human review required**: automated work reached its permitted boundary. This is expected for report approval and client delivery.
- **Not loaded**: the operator has not authenticated and loaded the evidence yet. This state is neutral.

## If a run appears stuck

1. Preserve the run ID.
2. Check whether the scanner is queued or running.
3. Use Recovery rather than starting a duplicate run.
4. Confirm frontend/backend release alignment.
5. Confirm the backend is reachable and semantically ready.
6. Inspect the correlation ID and operational events.
7. Check durable storage before assuming the run can survive a restart.
8. Rerun only after the existing run is terminal or explicitly unrecoverable.

## If everything says unavailable

Treat widespread unavailability as an infrastructure or configuration incident until proven otherwise.

Check:

- backend deployment status
- frontend API URL
- CORS origin configuration
- deployment-commit alignment
- database configuration and persistence
- scanner-worker binary availability
- GitHub repository reachability
- authorization metadata
- operations readiness blockers

Do not lift scores or replace unavailable states with green placeholders. Restore the evidence path and rerun the affected stage.

## Human review

A reviewer must verify:

- repository, customer, project, run, scan, and report identities
- evidence provenance and collection times
- unavailable and failed evidence
- score explanations
- repair recommendations and verification steps
- report hashes and review-packet identity where present
- whether client delivery is actually allowed

Approval must be an explicit human action. Requesting a review is not approval.

## Controlled delivery

Client delivery is allowed only when:

1. the reviewed draft is preserved;
2. the human decision is recorded;
3. a separate approved artifact is generated;
4. artifact identities and hashes verify;
5. durable storage requirements are satisfied;
6. controlled access is created by an authorized operator; and
7. receipt or acknowledgment evidence is recorded when required.

Revoke access when scope, recipient, expiration, or artifact identity is wrong.

## Deployment verification

After deployment or environment changes, run the hosted and operations readiness checks documented in the repository. HTTP 200 alone is insufficient. Verify the exact `main` SHA, Vercel deployment, Railway deployment, required routes, storage, scanners, and truth gates.

## Evidence integrity rules

- Missing evidence is not passing evidence.
- A green CI check does not prove the production deployment contains the same commit.
- A scanner exit code is not automatically a severity rating.
- A report is not client-ready because a PDF exists.
- A score must explain its evidence and limitations.
- Synthetic fixtures must be labeled synthetic.
- Live claims must be traceable to live evidence.

## Escalation record

For a failed or blocked production run, preserve:

- timestamp
- repository and authorized scope
- run ID and scan ID
- frontend and backend commit identities
- correlation ID
- failed stage
- exact error or blocker
- persistence adapter and durability status
- corrective action
- verification result

This record is part of NICO's repair memory and should be sufficient for another operator to reproduce the failure without guessing.
