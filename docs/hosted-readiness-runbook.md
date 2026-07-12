# NICO Hosted Readiness Runbook

This runbook explains how to use the hosted readiness and diagnostics surfaces without treating diagnostics as client approval.

## Scope

Use this runbook for authorized NICO hosted assessments only. The diagnostics pages, operations-readiness decision, and release-readiness summary are evidence-support tools. They do not approve delivery, lift scores by themselves, or replace human review.

## Primary pages

- `/diagnostics`: read-only diagnostics hub.
- `/scanner-runtime`: verifies deployed scanner runtime tool availability.
- `/release-readiness`: verifies that release-readiness support is installed and shows the expected output contract.
- `/operations/readiness`: fail-closed semantic readiness for deployment identity, report truth guard, durable storage, scanner execution, runtime configuration, and required routes.

## Terminal checks

Run the semantic readiness check first after every production deployment or environment change:

```bash
python scripts/check_operations_readiness.py https://YOUR-NICO-API-HOST
```

Then run the hosted smoke check:

```bash
python scripts/check_hosted_readiness.py https://YOUR-NICO-API-HOST
```

You can provide the API URL through an environment variable:

```bash
NICO_API_URL=https://YOUR-NICO-API-HOST python scripts/check_operations_readiness.py
NICO_API_URL=https://YOUR-NICO-API-HOST python scripts/check_hosted_readiness.py
```

The smoke check verifies:

- `/health` is reachable and reports `status=ok`.
- `/operations/readiness` is reachable and reports `status=ready`.
- `/diagnostics/hosted-scanner-runtime` is reachable.
- `/diagnostics/release-readiness` is reachable.

A successful operations-readiness decision proves that required production controls are present. Passing smoke checks prove endpoint reachability plus the required semantic status. Neither proves scanner output is clean, release evidence is complete, or client delivery is approved.

## Before running an assessment

1. Confirm the target repository is owned by the operator or explicitly authorized for review.
2. Confirm `/health` reports online.
3. Require `/operations/readiness` to report `ready`.
4. Run both terminal checks or open `/diagnostics` and review the diagnostic pages.
5. Open `/scanner-runtime` and verify whether scanner tools are installed or unavailable.
6. Treat unavailable tools as missing evidence, not clean results.

## Operations-readiness interpretation

- `ready`: all required and advisory operational checks passed.
- `degraded`: required controls passed, but advisory operator controls need attention.
- `blocked`: one or more required production controls failed or could not be verified.

Do not accept trusted production assessment traffic from a blocked deployment. Use `--allow-degraded` only for an explicitly approved diagnostic window; it does not authorize normal operator use or client delivery.

## Refresh Full Evidence workflow

1. Run a hosted Express assessment only after authorization is confirmed.
2. Request full evidence refresh when scanner evidence is needed.
3. Review scanner outputs for dependency, static, and secret tools.
4. Review Bandit triage status for blocking, needs-review, accepted-risk, false-positive, or fixed findings.
5. Review complexity evidence for source footprint, hotspots, churn, ownership, and velocity/complexity scoring support.
6. Review the evidence ledger for verified, partial, unavailable, and finding-bearing entries.
7. Review the release-readiness summary for score target state and remaining blockers.

## Readiness interpretation

A report is not client-ready just because runtime diagnostics or operations readiness are green. Client delivery remains blocked when any of the following are true:

- Required scanners are missing or unavailable.
- Scanner output is not current-run evidence.
- High-risk findings are unresolved or untriaged.
- Full-history secret scanning is unavailable or incomplete.
- Complexity evidence is missing or incomplete.
- Evidence ledger entries are partial, unavailable, or finding-bearing.
- Client final review roles are pending.
- Human review is still required.

## Minimum review checklist

Before client-facing delivery, verify:

- The evidence bundle hash is present.
- The evidence ledger hash is present.
- Markdown and HTML exports are hashed.
- Raw evidence JSON is hashed.
- Unavailable inventory is hashed.
- Full-detail export is attached.
- Release-readiness summary is attached.
- Technical reviewer signoff is complete.
- Delivery owner signoff is complete.
- Client or authorized representative signoff is complete.

## Guardrail

Do not treat any diagnostic page, operations-readiness result, score bridge, readiness summary, smoke-check result, or generated report as final approval. Final client delivery requires explicit human review and accepted signoff.
