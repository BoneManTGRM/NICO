# Safari Hosted App Notes

NICO hosted mode should keep all sensitive credentials on the backend. The browser may know the public backend URL, but it must never receive GitHub, API, or admin credentials.

## Frontend environment

Set the frontend backend pointer only:

```text
NEXT_PUBLIC_NICO_API_URL=https://nico-production-690a.up.railway.app
```

## Backend environment

Set CORS to the deployed frontend domains:

```text
NICO_CORS_ORIGINS=https://app.nicoaudit.com,https://nicoaudit.vercel.app
```

For private authorized repositories, configure a backend-only read-only GitHub credential using either the `NICO_GITHUB_TOKEN` or `GITHUB_TOKEN` environment variable. Do not paste real credentials into docs, frontend code, screenshots, or client reports.

Never expose GitHub credentials through the frontend.

## Backend start command

Use this command on the backend host:

```bash
uvicorn nico.api.main:app --host 0.0.0.0 --port $PORT
```
