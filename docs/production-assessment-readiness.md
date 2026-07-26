# Production assessment readiness

NICO must not create a Comprehensive assessment unless its exact run state can survive a backend replacement.

## Preferred production configuration: Postgres

1. Provision a managed Postgres service in the production environment.
2. Expose its private connection to the NICO backend as `DATABASE_URL` (Railway reference-variable form: `${{Postgres.DATABASE_URL}}`).
3. Keep `NICO_REQUIRE_DURABLE_ASSESSMENT_STORAGE=true`.
4. Redeploy the backend.
5. Verify `GET /diagnostics/comprehensive-runtime` reports:
   - `status: ready`
   - `persistence_adapter: postgres`
   - `survives_container_replacement_verified: true`
6. Confirm the frontend proxy reaches the same canonical backend origin for intake, continuation, status, review, and delivery.
7. Rerun Unified Production Acceptance and require two distinct successful Strategic run IDs bound to the deployed SHA.

## Supported fallback: verified persistent SQLite volume

Use this only when Postgres is intentionally unavailable.

1. Attach a durable volume to the NICO backend service.
2. Mount it at a stable location such as `/data`.
3. Set:
   - `NICO_ENABLE_SQLITE_DURABLE_STORAGE=true`
   - `NICO_REQUIRE_DURABLE_ASSESSMENT_STORAGE=true`
4. Do not set `NICO_COMPREHENSIVE_SQLITE_PATH` outside the mounted path.
5. Verify the platform exposes the mounted path through `RAILWAY_VOLUME_MOUNT_PATH` or set `NICO_DURABLE_VOLUME_PATH` to the exact mount.
6. Redeploy and verify the runtime diagnostic reports a mounted SQLite adapter and container-replacement safety.
7. Prove the same incomplete run can be read after replacing the backend container.

## Failure interpretation

- `comprehensive_durable_storage_required`: no supported durable adapter was configured.
- `comprehensive_sqlite_persistent_volume_required`: SQLite was enabled, but its path was not proven to survive container replacement.
- `assessment_backend_not_configured`: the frontend deployment has no safe canonical backend origin.
- `assessment_backend_configuration_conflict`: frontend backend variables point to more than one origin.
- `assessment_backend_unreachable`: the canonical backend did not respond after bounded retries.

These are deployment blockers. The application must fail before run creation, retain client-safe wording, and preserve detailed diagnostics for authorized operators and CI logs.
