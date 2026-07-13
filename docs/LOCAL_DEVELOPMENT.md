# Local Development

NICO supports direct Python/Node development and a Docker Compose workflow.

## Prerequisites

Direct setup:

- Python 3.10 or newer
- Node.js 20
- npm 10
- Git

Docker setup:

- Docker Engine with Compose v2

Optional external scanners improve evidence coverage. NICO must return unavailable evidence when an optional tool or required manifest is missing.

## Direct setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev,scanners]"
cp .env.example .env

nico --help
nico-api
```

In another terminal:

```bash
cd apps/web
cp .env.example .env.local
npm install --legacy-peer-deps
npm run dev
```

Open:

- frontend: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- health: `http://localhost:8000/health`

The installed `nico` command and `python -m nico` use the same dispatcher.

## Docker Compose

```bash
docker compose up --build
```

This starts:

- the complete production-route FastAPI application with reload on port 8000;
- the Next.js development server on port 3000;
- persistent local NICO data in the `nico-data` volume; and
- frontend dependencies in a separate named volume.

Stop services:

```bash
docker compose down
```

Remove local Compose data only when intentionally resetting development state:

```bash
docker compose down -v
```

## Verification

```bash
pytest

cd apps/web
npm run lint
npm run build
```

For package-entry verification:

```bash
python -m nico --help
nico --help
python run_local.py
nico-api
```

Do not run both API launch commands on the same port simultaneously.

## Environment variables

The root `.env.example` documents local storage, API, CORS, scanner, timeout, and production-only examples.

Important variables:

- `NICO_CORS_ORIGINS` — comma-separated allowed frontend origins
- `NICO_API_HOST` and `NICO_API_PORT` — local API binding
- `NICO_API_RELOAD` — local reload mode
- `NICO_DB_PATH` — local SQLite path
- `DATABASE_URL` — production durable database when configured
- `NICO_ENABLE_SCANNER_EXECUTION` — allow controlled scanner subprocesses
- `NICO_ALLOW_PROJECT_COMMANDS` — allow repository tests/build commands only in an adequately isolated worker

`NICO_ALLOWED_ORIGINS` is not the current CORS variable and must not be used.

## Safe test data

Use `nico/test_lab` and other explicitly synthetic fixtures. Never place real credentials or private client repositories into committed fixtures.

## Common failures

### Frontend says backend missing

Confirm `apps/web/.env.local` contains:

```text
NEXT_PUBLIC_NICO_API_URL=http://localhost:8000
```

Restart the Next.js process after changing the variable.

### Browser reports a CORS error

Confirm the backend uses:

```text
NICO_CORS_ORIGINS=http://localhost:3000
```

### API launcher import error

Use the current `python run_local.py` or installed `nico-api` command. Both start `nico.api.production:app`, which contains the complete route set.

### Scanner unavailable

Check the worker result. A missing binary, missing manifest, timeout, or disabled execution must remain unavailable or failed; do not convert it to passing evidence.
