# NICO — Neural Intelligence for Cyber Operations

NICO is an authorized, repair-first defensive cybersecurity and technical-assessment platform for repository evidence collection, drift detection, repair planning, verification, reporting, and repair memory.

NICO is not a basic scanner wrapper. Its core workflow binds an authorized target to an exact run, collects available evidence, executes supported defensive scanners, distinguishes unavailable or failed evidence, produces evidence-bound scoring and repair candidates, prepares reports, and stops at required human review before approval or client delivery.

## Current status

- Repository CI, security analysis, and deployment checks are required before release changes are merged.
- The canonical hosted assessment start is the unified Express, Mid, and Full page under `/assessment`.
- Vercel provides the Next.js frontend and Railway provides the FastAPI backend in the current hosted deployment model.
- A successful deployment does not prove an assessment result. Authorized production smoke runs and evidence review remain required.

See:

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — canonical architecture and truth contracts
- [`docs/OPERATOR_GUIDE.md`](docs/OPERATOR_GUIDE.md) — operating, recovery, review, and delivery procedures
- [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md) — stable, operational, experimental, legacy, and planned maturity
- [`docs/README.md`](docs/README.md) — documentation map

## Core capabilities

- **Local-first defensive scanning** — scans authorized local repositories and synthetic fixtures without requiring a hosted service.
- **No-server assessment mode** — assesses authorized local folders, GitHub repositories, archives, and passive-only local or staging URLs.
- **Unified assessment tiers** — Express, Mid, and Full share one normal intake while preserving different evidence-depth contracts.
- **Real external scanner execution** — the controlled worker executes supported tools when binaries and required manifests are available and returns explicit unavailable, failed, and timed-out states otherwise.
- **Built-in defensive checks** — identifies secret-exposure patterns, unsafe application-security markers, dependency risks, suspicious logs, identity-risk events, and AI-agent permission drift.
- **Exact-run evidence binding** — preserves repository, customer, project, run, scan, report, approval, and artifact identities.
- **Drift detection** — compares current evidence against stored baselines and records new or changed risk categories.
- **RYE repair scoring** — prioritizes findings using risk, exploitability, blast radius, verification availability, urgency, confidence, and recurrence memory.
- **TGRM repair candidates** — produces minimal, moderate, and strong repair options with verification and rollback guidance.
- **Verification workflow** — records scan and repair verification without treating a suggested repair as deployed.
- **Repair memory** — stores scans, findings, drift, repairs, verification, reports, policy, and audit history through the configured storage adapter.
- **Evidence-bound reporting** — produces structured JSON, Markdown, HTML, owner, developer, reparodynamic, compliance-oriented, and assessment reports where supported.
- **Human review and approved artifacts** — automated work stops at review; approval creates a separate integrity-bound artifact.
- **Controlled delivery** — supports expiring access, receipts, acknowledgments, and revocation for verified approved artifacts.
- **Governance policy** — keeps allowed, approval-required, and blocked actions explicit.
- **Operations and release readiness** — verifies deployment identity, durable storage, scanner execution, required routes, event health, alerts, and truth guards.

## Evidence and claim rules

NICO follows these rules:

1. Missing evidence is not passing evidence.
2. A queued or running scanner is not complete.
3. An unavailable tool is disclosed and receives no completion credit.
4. A score is an evidence signal, not a certification.
5. A generated PDF is not automatically approved or client-ready.
6. Synthetic fixtures must be labeled synthetic.
7. Live claims must remain traceable to live evidence.
8. Reparodynamics is an emerging framework used by this project; NICO does not represent it as independently validated academic science.

## Safety boundary

NICO is defensive-only software intended for systems the operator owns or is explicitly authorized to assess.

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

Production-impacting actions such as credential rotation, account disablement, data deletion, infrastructure deletion, DNS changes, broad firewall changes, production deployments, major dependency upgrades, or architecture rewrites require explicit human approval.

## Quick start

```bash
python -m pip install --upgrade pip
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

The test lab contains synthetic evidence and must not be described as a live client assessment.

## No-server authorized assessment

These commands do not require Railway, Vercel, Render, Fly.io, or `app.nicoaudit.com`:

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

Every non-demo assessment requires `--authorized`, confirming ownership or explicit permission.

See [`docs/NO_SERVER_ASSESSMENT.md`](docs/NO_SERVER_ASSESSMENT.md).

## Local API and frontend

Start the local API according to `run_local.py`, then open:

```text
http://localhost:8000/docs
```

Frontend development:

```bash
cd apps/web
npm install
npm run lint
npm run build
npm run dev
```

Open:

```text
http://localhost:3000
```

The frontend is an active operator application, not merely a placeholder foundation. The unified assessment flow, operations views, recovery, review, approval, delivery, diagnostics, and Retainer surfaces are at different maturity levels; see `docs/PROJECT_STATUS.md`.

## Hosted deployment

Deploy the frontend and backend separately:

- Frontend: Vercel or another compatible Next.js host using `apps/web`
- Backend: a Python host running the production FastAPI application
- Frontend environment: `NEXT_PUBLIC_NICO_API_URL=https://YOUR-NICO-API-HOST`
- Backend environment: `NICO_CORS_ORIGINS=https://YOUR-NICO-FRONTEND-HOST`

The hosted app is optional. Local-first assessment remains a supported operating mode.

See [`docs/SAFARI_HOSTED_APP.md`](docs/SAFARI_HOSTED_APP.md).

## Hosted readiness and release integrity

Operator surfaces include:

- `/diagnostics` — read-only diagnostics
- `/scanner-runtime` — deployed scanner availability
- `/release-readiness` — release and output-contract checks
- `/operations/readiness` — fail-closed semantic readiness
- frontend `/api/deployment` — frontend deployment identity

Run the backend checks after deployment or environment changes:

```bash
python scripts/check_operations_readiness.py https://YOUR-NICO-API-HOST
python scripts/check_hosted_readiness.py https://YOUR-NICO-API-HOST
```

Then run the GitHub Actions **Production Release Gate** for the intended `main` SHA and production Vercel and Railway origins.

HTTP reachability alone does not establish release integrity. The release gate must verify exact-SHA CI, deployment alignment, required routes, storage, scanners, and truth guards. None of these controls approves a report or replaces human review.

Relevant documents:

- [`docs/hosted-readiness-runbook.md`](docs/hosted-readiness-runbook.md)
- [`docs/OPERATIONS_READINESS.md`](docs/OPERATIONS_READINESS.md)
- [`docs/PRODUCTION_RELEASE_GATE.md`](docs/PRODUCTION_RELEASE_GATE.md)

## CLI commands

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

## Contributing and security

- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`SECURITY.md`](SECURITY.md)
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)

Do not open a public issue containing credentials, private client data, raw scanner secrets, delivery tokens, or practical exploitation details.

## License

NICO uses a dual-license model:

- `LICENSE` — source-available non-commercial license
- `COMMERCIAL_LICENSE.md` — commercial license template
- `docs/commercial-license-order-form.md` — commercial scope and terms template
- `docs/commercial-licensing-workflow.md` — commercial licensing workflow
- `docs/license-faq.md` — plain-language licensing FAQ

Commercial use is not allowed under the default non-commercial license. A separate written commercial license, order form, or agreement is required for business, government, client-facing, managed-service, hosted-service, consulting, paid-report, or other revenue-generating use.

Because the default license restricts commercial use, this repository is source-available and is not represented as open-source software.
