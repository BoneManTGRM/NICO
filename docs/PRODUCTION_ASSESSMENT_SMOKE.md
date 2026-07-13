# Production Assessment Smoke Proof

This procedure proves the deployed NICO frontend and canonical Express, Mid, and Full API routes without treating deployment reachability as assessment correctness.

## Safety boundary

Run this workflow only against a repository you own or are explicitly authorized to assess.

The workflow:

- requires an explicit authorization confirmation;
- performs exactly one assessment start request for each selected tier;
- never retries a start request automatically;
- uses only the exact returned Mid or Full `run_id` for continuation;
- polls the canonical status route instead of creating replacement runs;
- keeps unavailable, blocked, failed, and unrecognized states fail-closed;
- preserves the human-review and non-client-ready boundaries;
- does not require, print, or persist an admin token; and
- uploads a bounded JSON evidence artifact for review.

The workflow is manual-only. It is not scheduled because a real assessment can consume scanner, API, storage, and CI resources.

## Run through GitHub Actions

Open **Actions → Production Assessment Smoke → Run workflow** and provide:

- **API URL**: the deployed API origin, such as `https://your-api.example.com`;
- **Frontend URL**: optional deployed frontend origin;
- **Repository**: the explicitly authorized `owner/repository` target;
- **Tiers**: normally `express,mid,full`; and
- **Authorization confirmation**: enabled only after authorization is verified.

The workflow creates unique smoke customer and project identities from the GitHub Actions run identity. It does not use production client identifiers.

## Evidence artifact

The uploaded `production-assessment-smoke.json` records:

- the authorized repository and scope;
- the selected deployment origins;
- one start count per tier;
- the exact returned assessment or run identity;
- Mid and Full status-poll counts;
- proof that one exact status URL was used for each continued run;
- final response hashes rather than full potentially sensitive responses;
- final status and tier metadata; and
- whether human review remained required and client readiness remained false.

A failed run also uploads a bounded failure artifact. The artifact contains a safe error summary, not raw server traces, credentials, or scanner output.

## Local contract test

For localhost-only validation:

```bash
python scripts/production_assessment_smoke.py \
  --api-url http://127.0.0.1:8000 \
  --frontend-url http://127.0.0.1:3000 \
  --repository BoneManTGRM/NICO \
  --tiers express,mid,full \
  --confirm-authorized \
  --allow-http-localhost
```

HTTP is rejected for non-localhost targets.

## Interpretation

A passing smoke artifact proves that the selected deployment accepted one authorized start per tier, preserved exact continuation identity, returned recognized terminal states, and retained review boundaries at that time.

It does not prove:

- that every scanner was available;
- that every finding is correct;
- that a score is a certification;
- that the report is approved for delivery;
- that future deployments will behave identically; or
- that a frontend/backend deployment is correct merely because it returned HTTP 200.
