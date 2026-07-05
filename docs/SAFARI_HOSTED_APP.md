# NICO Safari Hosted App

This guide is for running NICO from Safari on phone and desktop without GitHub, VS Code, Codespaces, or localhost.

## Target setup

- Frontend: Vercel, using `apps/web`
- Backend API: a Python web service host such as Render, Railway, or Fly.io
- Code: GitHub repo `BoneManTGRM/NICO`
- Browser URL: a public HTTPS frontend URL

## Frontend environment

Set this environment variable in the frontend host:

```text
NEXT_PUBLIC_NICO_API_URL=https://YOUR-NICO-API-HOST
```

The frontend already reads `NEXT_PUBLIC_NICO_API_URL` and falls back to `http://localhost:8000` for local development.

## Backend environment

Set this environment variable in the backend host:

```text
NICO_CORS_ORIGINS=https://YOUR-NICO-FRONTEND-HOST
```

Use the exact frontend HTTPS URL. If you later add a custom domain, add both URLs separated by commas:

```text
NICO_CORS_ORIGINS=https://YOUR-NICO-FRONTEND-HOST,https://nico.yourdomain.com
```

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

## Smoke test

After both services deploy:

1. Open the backend `/health` URL and confirm it returns `status: ok`.
2. Open the frontend URL in Safari.
3. Confirm the UI loads without using `localhost`.
4. Use the frontend only on repos and systems you own or are authorized to assess.

## Notes

The hosted frontend can run in Safari. Full scanning requires a backend API URL. Local file scanning remains local-first unless a hosted backend is explicitly connected to authorized repositories or controlled test targets.
