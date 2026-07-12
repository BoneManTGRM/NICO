# NICO Production Release Gate

## Purpose

The production release gate is the only supported way to declare a NICO deployment last-known-good. It verifies the exact current `main` commit across source control, CI, Vercel, Railway, frontend identity, and backend semantic readiness.

A reachable URL is not sufficient. The gate fails closed when evidence is missing, stale, degraded, failed, or bound to a different commit.

The gate does not approve repository findings, raise assessment scores, or authorize client delivery. Final assessment delivery remains human-review-bound.

## Required evidence

The selected release SHA must be a full 40-character Git commit and must equal the current `main` head.

The exact SHA must have successful GitHub Actions runs for:

- NICO CI
- Node.js CI
- CodeQL Advanced
- Audit Evidence
- Security Audit Evidence
- Remediation Evidence

The commit must also have successful Vercel and Railway provider checks.

The deployed services must report:

- Railway backend `/operations/readiness`
  - schema `nico.operations_readiness.v1`
  - `status=ready`
  - `operational_ready=true`
  - deployed commit matching the selected release SHA
- Vercel frontend `/api/deployment`
  - schema `nico.frontend_deployment.v1`
  - `status=ok`
  - frontend commit matching the selected release SHA

The frontend and backend must therefore run the same exact release.

## Running the gate

Open GitHub Actions and manually run **Production Release Gate**.

Provide:

- `release_sha`: the full current `main` SHA
- `backend_url`: the public Railway backend HTTPS origin
- `frontend_url`: the public Vercel frontend HTTPS origin

The workflow uses the production GitHub environment so repository environment protection can require explicit approval.

The gate writes `release-manifest.json` and uploads it as a 90-day workflow artifact. The manifest includes:

- exact release and `main` identities;
- required workflow states;
- Vercel and Railway provider states;
- safe frontend and backend origins;
- deployed commit identities;
- backend readiness state and blocker IDs;
- every release-gate check;
- a stable release-identity SHA-256;
- a complete manifest SHA-256.

Raw credentials, provider response bodies, and embedded URL credentials are never included.

## Last-known-good record

When every check passes, the workflow creates a successful GitHub production deployment for the exact release SHA. This deployment record is the last-known-good reference and contains:

- release SHA;
- release-identity SHA-256;
- frontend environment URL;
- backend origin;
- workflow log URL.

A release is not last-known-good merely because Vercel or Railway reports a successful deployment. The complete NICO gate must pass and record the GitHub production deployment.

## Rollback procedure

1. Open GitHub **Deployments** and identify the latest successful NICO production deployment recorded by this gate.
2. Confirm its release SHA and release-identity SHA-256 against the uploaded manifest.
3. Redeploy the Vercel frontend from that exact SHA.
4. Redeploy the Railway backend from that exact SHA.
5. Do not mix the prior frontend with a newer backend, or the prior backend with a newer frontend.
6. Wait for both provider checks to finish.
7. Run **Production Release Gate** again with the rollback SHA and both production URLs.
8. Treat the rollback as complete only after the new gate run passes and records a successful production deployment.
9. Run a fresh Mid or Full acceptance assessment before resuming client delivery.

The gate intentionally requires the selected SHA to equal current `main`. When rolling back, first create and merge a normal revert commit so `main` represents the intended rollback state. Do not deploy an untracked historical commit behind current `main` and call it ready.

## Failure interpretation

Common blockers:

- `release_is_main_head`: the selected commit is stale or not merged to current `main`.
- `workflow_*`: a required workflow is missing, pending, failed, or bound to another SHA.
- `provider_vercel` or `provider_railway`: the deployment provider check is missing or unsuccessful.
- `backend_semantic_readiness`: Railway is reachable but operational prerequisites are blocked or degraded.
- `backend_release_sha`: Railway runs another commit.
- `frontend_release_sha`: Vercel runs another commit.
- `frontend_backend_alignment`: frontend and backend are not the same release.
- `last_known_good_record`: the release passed but GitHub deployment recording failed, usually because deployment-write permission or environment configuration is incomplete.

Resolve every blocker and rerun the complete workflow. Never edit a failed manifest into a successful one.

## Local diagnostic use

The same checker can be run locally with a GitHub token that can read Actions, checks, and statuses:

```bash
GITHUB_TOKEN=... python scripts/check_production_release.py \
  --repository BoneManTGRM/NICO \
  --sha FULL_CURRENT_MAIN_SHA \
  --backend-url https://YOUR-RAILWAY-BACKEND \
  --frontend-url https://YOUR-VERCEL-FRONTEND \
  --output release-manifest.json
```

Omit `--record-deployment` for local diagnostics. A local pass does not replace the protected GitHub workflow or create a last-known-good record.
