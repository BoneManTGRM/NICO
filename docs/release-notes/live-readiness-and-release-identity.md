# Live readiness and release identity repair

## Incident

The production custom domain displayed an older assessment bundle while GitHub reported a newer Vercel deployment as successful. The live backend also rejected assessment creation because SQLite durability could not be proven across container replacement.

These are separate release failures:

1. **Frontend release mismatch:** `app.nicoaudit.com` did not serve the exact successful Vercel commit.
2. **Backend persistence blocker:** the assessment runtime correctly refused to create a run without Postgres or verified mounted SQLite storage.

## Repository repairs

- No-run readiness failures remain beside the engagement action and no longer create a large, repetitive engagement-status workspace.
- The frontend exposes `/api/release` with the exact Vercel commit SHA and a stable UI contract identifier.
- Production release proof verifies that the custom domain serves the exact successful Vercel deployment and rejects stale assessment copy.
- SQLite persistence can be proven from a configured volume path or a detected non-ephemeral Linux mount.
- Overlay, root, tmpfs, ramfs, and other ephemeral filesystems remain fail-closed.

## Required hosting configuration

If production diagnostics still report `comprehensive_sqlite_persistent_volume_required`, complete one of these deployment actions:

### Preferred: Postgres

1. Attach a Postgres service to the Railway project.
2. Expose its private connection URL to the NICO backend as one supported variable: `DATABASE_URL`, `DATABASE_PRIVATE_URL`, `POSTGRES_URL`, `POSTGRES_PRIVATE_URL`, `RAILWAY_DATABASE_URL`, or `RAILWAY_POSTGRES_URL`.
3. Ensure `NICO_DISABLE_POSTGRES` is absent or false.
4. Redeploy the backend.

### Supported fallback: mounted SQLite

1. Attach a Railway persistent volume to the NICO backend service.
2. Mount it at `/data`, matching the Docker image's `NICO_SQLITE_PATH=/data/nico-runtime.sqlite3`, or set `RAILWAY_VOLUME_MOUNT_PATH`/`NICO_DURABLE_VOLUME_PATH` to the actual mount.
3. Redeploy the backend.

Do not set `NICO_SQLITE_PERSISTENCE_CONFIRMED=true` unless the deployer has independently verified that the configured SQLite path is on deployment-surviving storage.

## Acceptance

Production is ready only when:

- `/api/release` returns the exact main-branch release SHA and `ui_contract: expert-engagement-v2`.
- `/api/nico/diagnostics/comprehensive-runtime` returns `status: ready`.
- `survives_container_replacement_verified` is true.
- Two consecutive Strategic assessments complete against the same deployed SHA.
