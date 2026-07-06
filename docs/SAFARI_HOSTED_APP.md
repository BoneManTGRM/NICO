# NICO Safari Hosted App

This guide is for running NICO from Safari on phone and desktop without GitHub, VS Code, Codespaces, or localhost.

## Target setup

- Frontend: Vercel, using `apps/web`
- Backend API: a Python web service host such as Render, Railway, or Fly.io
- Code: GitHub repo `BoneManTGRM/NICO`
- Browser URL: `https://app.nicoaudit.com`

## Safety boundary

NICO hosted mode is defensive-only and authorized-access-only.

Hosted mode must not perform unauthorized scanning, exploitation, credential theft, phishing, malware, stealth, evasion, persistence, destructive actions, authentication bypass, or offensive attack automation.

Hosted repository assessment is read-only. Production-impacting repairs require human approval.

## Frontend environment

Set this environment variable in the frontend host:

```text
NEXT_PUBLIC_NICO_API_URL=https://YOUR-NICO-API-HOST
```

The frontend reads `NEXT_PUBLIC_NICO_API_URL` and falls back to `http://localhost:8000` for local development.

## Backend environment

Set this environment variable in the backend host:

```text
NICO_CORS_ORIGINS=https://app.nicoaudit.com,https://nicoaudit.vercel.app
```

For private authorized repositories, set one of these on the backend only:

```text
NICO_GITHUB_TOKEN=YOUR_READ_ONLY_GITHUB_TOKEN
```

or:

```text
GITHUB_TOKEN=YOUR_READ_ONLY_GITHUB_TOKEN
```

Never expose GitHub tokens through the frontend.

## Backend start command

Use this command on the backend host:

```bash
uvicorn nico.api.main:app --host 0.0.0.0 --port $PORT
```

## Backend build command

Use this command on the backend host:

```bash
pip install -r requirements.txt
```

## Vercel frontend settings

Use these settings when importing the GitHub repo:

```text
Project root: apps/web
Framework: Next.js
Build command: npm run build
Install command: npm install
```

## Cloudflare / Vercel domain

For `app.nicoaudit.com`, Vercel should own the frontend deployment target while Cloudflare only provides DNS.

Use the Vercel-provided CNAME target in Cloudflare:

```text
Type: CNAME
Name: app
Target: 1b5fbc4f87411069.vercel-dns-017.com
Proxy status: DNS only
TTL: Auto
```

## Hosted backend deploy checklist

### Render

- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn nico.api.main:app --host 0.0.0.0 --port $PORT`
- Environment:
  - `NICO_CORS_ORIGINS=https://app.nicoaudit.com,https://nicoaudit.vercel.app`
  - optional `NICO_GITHUB_TOKEN` for private repos

### Railway

- Add the repo as a Python service.
- Set the start command to `uvicorn nico.api.main:app --host 0.0.0.0 --port $PORT`.
- Add the same environment variables listed above.

### Fly.io

- Use the same command and environment values.
- Confirm the public HTTPS hostname works before connecting it to Vercel.

## Smoke test

After both services deploy:

1. Open the backend `/health` URL and confirm it returns `status: ok`.
2. In Vercel, set `NEXT_PUBLIC_NICO_API_URL` to the backend HTTPS URL.
3. Redeploy the frontend.
4. Open `https://app.nicoaudit.com` in Safari.
5. Confirm the System Status section shows API online.
6. Run an authorized repository assessment.
7. Confirm each report section includes evidence or an unavailable-data note.

## Hosted assessment endpoints

```text
GET  /health
POST /assessment/github
GET  /assessment/latest
```

`POST /assessment/github` requires explicit authorization in the request body. It accepts a GitHub `owner/name` value or repository URL, pulls read-only GitHub metadata and repository files, and returns an Express Technical Health Assessment report with Markdown and HTML exports.

## Notes

The hosted frontend can run in Safari. Full hosted assessment requires a backend API URL. Local file scanning remains local-first unless a hosted backend is explicitly connected to authorized repositories or controlled test targets.
