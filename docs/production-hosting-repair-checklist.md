# Production hosting repair checklist

Use this checklist when the public assessment page shows stale copy or the assessment service reports unavailable storage.

## Vercel custom domain

- Confirm the Vercel project connected to `BoneManTGRM/NICO` uses `main` as its production branch.
- Confirm the project root directory is `apps/web`.
- Confirm `app.nicoaudit.com` is assigned to that same project and its production environment, not an older project or preview deployment.
- Remove conflicting domain assignments before reattaching the domain.
- Redeploy the exact main-branch SHA.
- Verify `https://app.nicoaudit.com/api/release` returns the exact SHA and `ui_contract: expert-engagement-v2`.

## Railway persistence

Complete one supported persistence configuration.

### Postgres

- Attach a Postgres service.
- Reference its private URL from the NICO backend using a supported environment variable.
- Confirm `NICO_DISABLE_POSTGRES` is false or absent.

### Persistent SQLite volume

- Attach a Railway volume to the NICO backend.
- Mount the volume at `/data`, or set the durable-volume path variables to the actual mount.
- Keep the SQLite database inside that mount.

## Verification

- Redeploy the backend.
- Check `/api/nico/diagnostics/comprehensive-runtime`.
- Require `status: ready` and `survives_container_replacement_verified: true`.
- Run Unified Production Acceptance and require two consecutive successful assessments.
