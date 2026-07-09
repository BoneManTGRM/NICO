# Refresh Full Evidence

The Refresh Full Evidence page is a one-click hosted workflow for re-running the Express assessment path with the strongest evidence collection settings available in hosted mode.

Path:

```text
/refresh-full-evidence
```

The page sends an authorized assessment request to the hosted backend with these intent flags:

```json
{
  "assessment_mode": "express",
  "run_scanner_worker": true,
  "scanner_worker_autorun": true,
  "full_history_secret_scan": true,
  "refresh_full_evidence": true
}
```

The backend remains evidence-bound. The refresh flow does not invent clean scanner results, does not hide unavailable tools, and does not remove human review requirements by itself.

## Expected evidence path

A successful refresh attempts to rebuild the report using:

- Dependency evidence: `pip-audit`, `npm-audit`, `osv-scanner`
- Static evidence: `bandit`, `semgrep`, `eslint`, `typescript`
- Secret evidence: full-history `gitleaks` and `trufflehog`
- Bandit triage evidence when Bandit findings are present
- Complexity evidence bound to the current report run
- Evidence ledger coverage for the current report
- Final trust gates and report export truth gates

## UI checklist

The page shows a section-level readiness checklist for:

- Dependency scanners
- Full-history secrets
- Static analysis
- Complexity / velocity

A section is treated as verified when either the evidence ledger marks that section complete or the returned report section is green with no unavailable evidence.

## Guardrails

- Authorization checkbox is required before the button is enabled.
- Missing tools remain visible as missing or unavailable evidence.
- Findings remain visible and still require repair or triage.
- PDF download is enabled only when the returned report includes a refreshed PDF payload.
- Human review remains required when the backend report says it is required.
