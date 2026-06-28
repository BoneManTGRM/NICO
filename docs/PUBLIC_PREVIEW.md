# NICO Public Preview

This document explains what the public NICO preview is, where it lives, how to update it safely, and how it differs from the local dashboard and any future hosted SaaS version.

Public page: <https://bonemantgrm.github.io/NICO/>

## What the public preview is

The GitHub Pages page is a static public preview of the NICO Command Center.

It is a product, landing, and dashboard preview. It does not run scans, connect to private repositories, store data, call the backend, use secrets, or represent a live SaaS deployment.

## What NICO is

NICO = Neural Intelligence Cyber Operations

Tagline: Autonomous cyber defense through Reparodynamics.

Core value: NICO scans authorized local repositories, detects cyber drift, ranks repair value with RYE, generates TGRM repair plans, verifies outcomes, and stores repair memory.

## Public preview file locations

The public-preview content is currently kept in these locations:

- `index.html`
- `docs/dashboard-preview/index.html`
- `gh-pages/index.html` if the `gh-pages` branch exists and is used as the GitHub Pages source

Keep these public-preview pages visually consistent so the public site does not drift depending on which Pages source is active.

## GitHub Pages source guidance

Preferred stable Pages source:

- Source: Deploy from branch
- Branch: `gh-pages`
- Folder: `/root`

Backup option:

- Workflow: `.github/workflows/pages-dashboard-preview.yml`
- Trigger only:

```yaml
on:
  workflow_dispatch:
```

Use the manual GitHub Actions deployment only if repository Pages settings are intentionally configured to GitHub Actions.

If GitHub Pages settings cannot be read through the available tools, do not guess. Manually confirm this path in GitHub:

Repo -> Settings -> Pages -> Source -> Deploy from branch -> `gh-pages` / `/root`.

## Why the Pages workflow is manual-only

The Pages deploy workflow is manual-only because the static preview already exists in repository files and automatic Pages deploy runs were failing. Making the workflow manual-only prevents repeated failed deploy runs after dashboard preview edits.

Historical failed Actions runs remain in Actions history. This documentation does not claim that older failed runs were fixed retroactively.

## Safe public preview update checklist

- Update root `index.html` first.
- Mirror the same visual and content changes into `docs/dashboard-preview/index.html`.
- If `gh-pages/index.html` exists and is used, mirror the same content there.
- Do not add API calls.
- Do not add analytics.
- Do not add external scripts.
- Do not expose secrets.
- Do not imply live scanning.
- Keep all examples fake, demo-only, or masked.
- Confirm the public page still says static preview only.

## Static preview vs local dashboard vs future SaaS

| Area | Status | Runtime | Data | Notes |
| --- | --- | --- | --- | --- |
| Static GitHub Pages preview | Public | Static HTML/CSS/inline JavaScript | No backend, no scans, no private data | Product and dashboard preview only |
| Local dashboard | Local machine | FastAPI backend plus `apps/web` frontend | Can run demo scans | Intended for authorized local repositories |
| Future SaaS | Not deployed yet | Future hosted frontend/backend/database | Requires production controls | Requires auth, RBAC, tenant isolation, encrypted server-side secret storage, audit logs, and approval workflows |

Do not deploy a hosted SaaS version until PR #1 is green, merged, and production hardening is complete.

## Current local run commands

Backend:

```bash
git clone https://github.com/BoneManTGRM/NICO.git
cd NICO
pip install -r requirements.txt
python -m nico scan-test-lab
python -m nico scan-drift-demo
python -m nico report latest
python -m nico verify latest
python run_local.py
```

Frontend:

```bash
cd apps/web
npm install
npm run dev
```

Local URLs:

- Dashboard: <http://localhost:3000>
- API docs: <http://localhost:8000/docs>

## Defensive-only boundary

NICO is designed to help owners improve systems they are authorized to protect.

The public preview must not include:

- unauthorized scanning language
- exploit instructions
- credential theft guidance
- phishing instructions
- malware logic
- stealth/evasion instructions
- destructive actions
- authentication bypass instructions
- real target examples

Allowed public-preview wording:

- authorized local repositories
- safe demo fixtures
- masked evidence
- defensive-only
- human approval required
- static preview
- future hosted deployment
