# NICO - Neural Intelligence for Cyber Operations

Autonomous repair-first cybersecurity platform for local-first defensive analysis, drift detection, repair planning, and verification.

NICO is designed for authorized security work only. It focuses on finding defensive risk, ranking what should be repaired first, generating targeted repair plans, verifying outcomes, and preserving repair memory over time.

## Status

CI guard active and passing.

Last verified: 2026-07-12

## Core Features

- **Local-first repository scanning** - scans authorized local repositories and safe test fixtures without requiring a hosted service.
- **No-server authorized assessment mode** - assesses authorized local folders, GitHub repositories, archives, and passive-only local/staging URLs without a public backend.
- **Built-in defensive scanners** - detects secret exposure patterns, unsafe application-security markers, risky dependency fixtures, suspicious log patterns, identity-risk events, and AI-agent permission drift.
- **Optional external scanner awareness** - checks availability for tools such as gitleaks, trufflehog, osv-scanner, pip-audit, npm, OpenSSF Scorecard, semgrep, bandit, and eslint.
- **Drift detection** - compares current scan output against a stored baseline and flags risk-score drift or new drift categories.
- **RYE repair scoring** - ranks findings by severity, exploitability, blast radius, verification availability, urgency, confidence, and recurrence memory.
- **TGRM repair candidates** - creates minimal, moderate, and strong repair options with verification commands, rollback guidance, and Codex-ready patch prompts.
- **Verification workflow** - supports latest-scan verification and repair-specific verification tracking.
- **Repair memory** - stores scans, findings, drift events, repair candidates, verification results, reports, policy state, and audit logs in a local SQLite-backed store.
- **Multi-format reporting** - generates JSON, Markdown, HTML, owner, developer, reparodynamic, compliance-oriented, and no-server Express Technical Health Assessment reports.
- **Governance policy** - keeps allowed actions, approval-required actions, blocked actions, autonomy level, and kill-switch behavior explicit.
- **Local API** - exposes FastAPI endpoints for local scans, findings, drift, repairs, verification, memory, reports, policy, and audit logs.
- **Frontend foundation** - includes a local Next.js web app foundation under `apps/web`.
- **Technical assessment mode** - provides an express assessment path with optional GitHub activity, token-health, dependency, CI/CD, architecture, maturity, resourcing, roadmap, and synthesis modules when available.
- **Semantic operations readiness** - distinguishes basic process liveness from production prerequisites such as deployment identity, durable storage, scanner execution, truth guards, runtime configuration, and required workflow routes.

## Safety Boundary

NICO is defensive-only software. It is intended for systems the operator owns or is explicitly authorized to assess.

NICO does **not** perform or authorize:

- unauthorized scanning
- exploitation
- credential theft
- phishing
- malware
- stealth or evasion
- persistence
- destructive actions
- authentication bypass
- offensive attack automation

Production-impacting actions such as credential rotation, account disablement, data deletion, infrastructure deletion, DNS changes, broad firewall changes, production deployments, major dependency upgrades, or architecture rewrites require human approval.

## Quick Start

```bash
pip install -r requirements.txt
python -m nico scan-test-lab
python -m nico scan-drift-demo
python -m nico report latest
python -m nico verify latest
python -m nico memory
python -m nico policy show
pytest
python run_local.py
```

## No-Server Authorized Assessment

Run these commands without a hosted backend, paid server, Render, Railway, Fly.io, or `app.nicoaudit.com`.

```bash
python -m nico assess local /path/to/project --authorized
python -m nico assess github owner/repo --authorized
python -m nico assess archive ./project.zip --authorized
python -m nico assess url https://staging.example.com --passive-only --authorized
python -m nico assess latest
python -m nico assess report latest --format markdown
python -m nico assess report latest --format html
python -m nico assess verify latest
```

Every non-demo assessment requires `--authorized`, confirming that you own the target or have explicit permission to assess it.

See `docs/NO_SERVER_ASSESSMENT.md` for the full no-server workflow.

Open local API docs at:

```text
http://localhost:8000/docs
```

Frontend:

```bash
cd apps/web
npm install
npm run lint
npm run build
npm run dev
```

Open the local frontend at:

```text
http://localhost:3000
```

## Hosted Safari App

For a phone/desktop browser setup without localhost, deploy the frontend and backend separately:

- Frontend: Vercel or another Next.js host using `apps/web`
- Backend API: a Python web service host
- Frontend environment: `NEXT_PUBLIC_NICO_API_URL=https://YOUR-NICO-API-HOST`
- Backend environment: `NICO_CORS_ORIGINS=https://YOUR-NICO-FRONTEND-HOST`

The hosted app is optional. The no-server assessment engine works locally first.

See `docs/SAFARI_HOSTED_APP.md` for the full hosted setup.

## Hosted Readiness Diagnostics

Hosted readiness support is available for operators who need current-run evidence visibility before client review.

- `/diagnostics` - read-only diagnostics hub.
- `/scanner-runtime` - deployed scanner runtime tool availability.
- `/release-readiness` - release-readiness support and output-contract verification.
- `/operations/readiness` - fail-closed semantic production readiness for deployment identity, truth guards, durable storage, scanner execution, runtime configuration, and required routes.
- Frontend `/api/deployment` - safe Vercel deployment-commit identity used to detect stale frontend/backend combinations.
- `docs/hosted-readiness-runbook.md` - operator runbook for Refresh Full Evidence review, readiness blockers, evidence hashes, and human signoff checks.
- `docs/OPERATIONS_READINESS.md` - production operations-readiness contract and failure procedure.
- `docs/PRODUCTION_RELEASE_GATE.md` - exact-SHA CI, Vercel, Railway, deployment-alignment, last-known-good, and rollback procedure.

Run both backend checks after deployment or environment changes:

```bash
python scripts/check_operations_readiness.py https://YOUR-NICO-API-HOST
python scripts/check_hosted_readiness.py https://YOUR-NICO-API-HOST
```

Then manually run the GitHub Actions **Production Release Gate** for the full current `main` SHA and the production Vercel and Railway origins. A release becomes last-known-good only when that fail-closed gate passes and records a successful GitHub production deployment.

The operations checker fails unless semantic readiness is `ready`. The hosted smoke check validates both endpoint reachability and required semantic status. The production release gate additionally requires exact-SHA CI and deployment alignment. None of these controls approve delivery, lift scores by themselves, or replace human review. Treat unavailable tools and unresolved findings as blockers until they are fixed, verified, or explicitly triaged.

## License

NICO uses a dual-license model:

- `LICENSE` - source-available non-commercial license for personal, educational, internal evaluation, testing, and non-commercial defensive research use.
- `COMMERCIAL_LICENSE.md` - commercial license template for business, government, client-facing, managed-service, hosted-service, consulting, paid report, or other revenue-generating use.
- `docs/commercial-license-order-form.md` - order form template for defining customer scope, seats, term, fees, support, and special terms.
- `docs/commercial-licensing-workflow.md` - step-by-step checklist for moving from commercial interest to signed scope.
- `docs/license-faq.md` - plain-language licensing FAQ for evaluators and buyers.

Commercial use is not allowed under the default non-commercial license. A separate written commercial license, order form, or signed agreement is required before using NICO for commercial work.

This repository is not licensed as open-source software because the default license restricts commercial use.

## CLI Commands

```bash
python -m nico scan <local-path>
python -m nico scan-test-lab
python -m nico scan-drift-demo
python -m nico assess local <path> --authorized
python -m nico assess github <owner/repo> --authorized
python -m nico assess archive <archive-path> --authorized
python -m nico assess url <url> --passive-only --authorized
python -m nico assess report latest --format markdown
python -m nico report latest
python -m nico verify latest
python -m nico memory
python -m nico policy show
```
