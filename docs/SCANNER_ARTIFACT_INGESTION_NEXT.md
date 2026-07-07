# Scanner Artifact Ingestion Follow-Up

## Goal

Raise NICO Express scores by consuming real scanner artifacts that already exist in GitHub Actions output.

## Artifacts to ingest

- `security-audit-evidence/credential-scan.json`
- `security-audit-evidence/bandit.json`
- `security-audit-evidence/semgrep.json`
- `security-audit-evidence/pip-audit.json`
- `security-audit-evidence/npm-audit.json`
- `audit-evidence-results/pip-audit-results.json`
- `audit-evidence-results/npm-audit-results.json`

## Section mapping

- Clean `credential-scan.json` -> stronger Secrets Exposure Review evidence.
- Clean `bandit.json` and `semgrep.json` -> stronger Static Analysis evidence.
- Clean `pip-audit` and `npm-audit` artifacts -> stronger Dependency / Library Ecosystem evidence.
- Failed, stale, missing, or unavailable artifacts must remain visible and must not be treated as passing.

## Expected score effects

- Dependency health improves only after npm audit findings are actually fixed.
- Secrets review can move higher when credential-scan artifacts prove no high-confidence findings.
- Static analysis can move higher when Bandit/Semgrep artifacts prove clean or low-risk results.
- CI/CD can move higher when workflow evidence artifacts are current and successful.

## Safety boundary

This remains defensive-only and authorized-repository only. NICO must not scan third-party systems or claim scanner-clean status without the corresponding parsed artifact contents.
