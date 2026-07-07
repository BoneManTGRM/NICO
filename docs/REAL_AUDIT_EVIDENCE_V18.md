# Real Audit Evidence v18

This update moves NICO score improvement away from score tuning and toward real audit-evidence collection.

## Added workflow

`.github/workflows/security-audit.yml`

The workflow collects evidence for:

- `pip-audit` dependency audit.
- `npm audit` critical dependency audit.
- `Bandit` Python static analysis.
- `Semgrep` static analysis.
- A high-confidence credential-pattern scan for private keys, GitHub tokens, and AWS access keys.

Audit artifacts are uploaded as `security-audit-evidence`.

## Report scoring effect

When Express sees the security-audit workflow in the repository workflow list, report accuracy can treat Secrets, Dependencies, and Static Analysis as having stronger CI-backed evidence collection configured.

This can raise provisional scores while still keeping unavailable evidence visible.

## Safety rule

This does not claim the repository is fully clean. Artifact review and human review are still required before client-facing delivery.

## Expected score movement

If the workflow is present and no section has confirmed findings:

- Dependency / Library Ecosystem can move toward green.
- Secrets Exposure Review can move toward green.
- Static Analysis can strengthen.
- Overall score should move more than previous score-only updates.
