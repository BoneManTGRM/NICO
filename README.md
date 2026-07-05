# NICO - Neural Intelligence for Cyber Operations

Autonomous repair-first cybersecurity platform for local-first defensive analysis, drift detection, repair planning, and verification.

NICO is designed for authorized security work only. It focuses on finding defensive risk, ranking what should be repaired first, generating targeted repair plans, verifying outcomes, and preserving repair memory over time.

## Status

CI guard active and passing.

Last verified: 2026-07-05

## Core Features

- **Local-first repository scanning** - scans authorized local repositories and safe test fixtures without requiring a hosted service.
- **Built-in defensive scanners** - detects secret exposure patterns, unsafe application-security markers, risky dependency fixtures, suspicious log patterns, identity-risk events, and AI-agent permission drift.
- **Optional external scanner awareness** - checks availability for tools such as gitleaks, trufflehog, osv-scanner, pip-audit, npm, OpenSSF Scorecard, semgrep, bandit, and eslint.
- **Drift detection** - compares current scan output against a stored baseline and flags risk-score drift or new drift categories.
- **RYE repair scoring** - ranks findings by severity, exploitability, blast radius, verification availability, urgency, confidence, and recurrence memory.
- **TGRM repair candidates** - creates minimal, moderate, and strong repair options with verification commands, rollback guidance, and Codex-ready patch prompts.
- **Verification workflow** - supports latest-scan verification and repair-specific verification tracking.
- **Repair memory** - stores scans, findings, drift events, repair candidates, verification results, reports, policy state, and audit logs in a local SQLite-backed store.
- **Multi-format reporting** - generates JSON, Markdown, HTML, owner, developer, reparodynamic, and compliance-oriented reports.
- **Governance policy** - keeps allowed actions, approval-required actions, blocked actions, autonomy level, and kill-switch behavior explicit.
- **Local API** - exposes FastAPI endpoints for local scans, findings, drift, repairs, verification, memory, reports, policy, and audit logs.
- **Frontend foundation** - includes a local Next.js web app foundation under `apps/web`.
- **Technical assessment mode** - provides an express assessment path with optional GitHub activity, token-health, dependency, CI/CD, architecture, maturity, resourcing, roadmap, and synthesis modules when available.

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

## CLI Commands

```bash
python -m nico scan <local-path>
python -m nico scan-test-lab
python -m nico scan-drift-demo
python -m nico report latest
python -m nico report owner
python -m nico report developer
python -m nico report reparodynamic
python -m nico report compliance
python -m nico verify latest
python -m nico verify --repair-id <repair_id>
python -m nico memory
python -m nico policy show
python -m nico scanner-availability
python -m nico assessment <target> --tier express --mode audit
```

## Current Limitations

- NICO is an early local-first defensive platform foundation.
- External scanners are optional and depend on local installation and environment availability.
- Mid-tier and full-tier assessment paths are still future phases unless implemented by active modules.
- Compliance reports are local mapping reports only and are not certifications.
- Hosted SaaS features such as authentication, RBAC, tenant isolation, billing, and encrypted cloud secret storage are not part of the current local-first foundation.
- NICO should not be used against third-party systems without explicit written authorization.

## License

Copyright © 2026 Cody Ryan Jenkins. All rights reserved.

This repository is public for visibility and development tracking. No license is granted to copy, modify, distribute, sublicense, or use this software commercially without written permission.
