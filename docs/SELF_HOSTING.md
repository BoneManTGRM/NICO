# NICO Self-Hosting

This guide covers a single-host defensive deployment for systems the operator owns or is explicitly authorized to assess. It does not authorize scanning third-party systems, automatic production repair, or client delivery without review.

## Supported deployment shapes

### Docker Compose

The repository Compose file starts:

- the FastAPI production bootstrap on port `8000`
- the Next.js development frontend on port `3000`
- a named Docker volume at `/data` for SQLite lifecycle and report records

Start it with:

```bash
docker compose up --build
```

Open:

```text
http://localhost:3000
http://localhost:8000/docs
```

The API service uses `nico.api.production_bootstrap:app`, not the lower-level compatibility modules. The bootstrap fails closed if required assessment routes, scanner/report gates, lifecycle protections, or serialization protections are not installed.

### API-only container

```bash
docker build -t nico .
docker run --rm \
  -p 8000:8000 \
  -v nico-data:/data \
  -e NICO_SQLITE_DURABLE_MOUNT_VERIFIED=true \
  nico
```

A writable container directory is not automatically durable. Set `NICO_SQLITE_DURABLE_MOUNT_VERIFIED=true` only when `/data` is backed by a persistent volume. For multi-instance or higher-assurance deployments, configure Postgres through `DATABASE_URL`.

## Required configuration

| Variable | Purpose |
|---|---|
| `NICO_GITHUB_TOKEN` or `GITHUB_TOKEN` | Authorized GitHub API access, including private repositories when permitted. |
| `NICO_ADMIN_TOKEN` | Protects operator-only recovery and diagnostic actions. Do not expose it to browsers or logs. |
| `NICO_CORS_ORIGINS` | Comma-separated allowed frontend origins. |
| `DATABASE_URL` | Optional Postgres lifecycle storage. Recommended for deployments that must survive container replacement and scale beyond one process. |
| `NICO_SQLITE_PATH` | SQLite lifecycle path when Postgres is not configured. Compose uses `/data/nico-runtime.sqlite3`. |
| `NICO_SQLITE_DURABLE_MOUNT_VERIFIED` | Explicit operator attestation that the SQLite parent path is a persistent mount. |
| `NICO_WEB_WORKERS` | Uvicorn process count. Keep `1` while assessment execution remains in-process. |
| `NICO_ALLOW_PROJECT_COMMANDS` | Controls authorized project-command execution. Leave false unless the deployment has a reviewed sandbox boundary. |

## Production frontend

The repository Compose frontend is intended for local development. A production frontend should:

1. build `apps/web` with `npm ci` and `npm run build`;
2. set `NICO_API_URL` or `NEXT_PUBLIC_NICO_API_URL` to the HTTPS API origin;
3. restrict the same-origin proxy to the canonical assessment and bounded diagnostic routes;
4. configure the API CORS allowlist for the deployed frontend origin.

## Storage truth

- **Memory**: process-local and not restart durable.
- **SQLite on an unverified path**: writable recording only; it may disappear when a container is replaced.
- **SQLite on a verified persistent volume**: single-host durable recording.
- **Postgres**: preferred for restart proof, multi-process access, and operational recovery.

Do not describe a run as durable solely because a record was written successfully.

## Scanner installation

Hosted scanner binaries are downloaded from allowlisted GitHub release assets at pinned release tags. See [`SCANNERS.md`](SCANNERS.md). Build with `NICO_SCANNER_INSTALL_STRICT=true` when a missing pinned scanner must fail the image build.

## Verification

After startup:

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/diagnostics/express-runtime
curl -fsS http://localhost:8000/diagnostics/mid-runtime
```

Review the responses for blocked runtime contracts, missing routes, unavailable storage, or scanner/report gate failures before starting an authorized assessment.

## Upgrade procedure

1. Back up persistent lifecycle storage.
2. Record the current image or commit SHA.
3. Build and run repository CI before deployment.
4. Deploy the intended exact SHA.
5. Verify API and frontend deployment identity.
6. Execute one authorized smoke assessment for each tier being released.
7. Retain the exact run, scan, report, and deployment identities.
8. Roll back if the new deployment weakens authorization, evidence, review, storage, or delivery boundaries.

See [`PRODUCTION_RELEASE_GATE.md`](PRODUCTION_RELEASE_GATE.md) and [`OPERATOR_GUIDE.md`](OPERATOR_GUIDE.md).
