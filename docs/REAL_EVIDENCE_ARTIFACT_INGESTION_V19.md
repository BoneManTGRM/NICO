# Real Evidence Artifact Ingestion v19

## Purpose

v19 makes Express scoring depend on real CI and audit artifact contents instead of workflow presence alone.

PR #34 added artifact collection. PR #35 added regression coverage for the scoring path. v19 adds the parser and scoring bridge that turns artifact contents into report evidence.

## Evidence sources

NICO expects these artifact families:

- `audit-results` from `NICO CI` for Python dependency audit output.
- `frontend-audit-results` from `Node CI` for frontend npm audit output.
- `audit-evidence-results` from `Audit Evidence` for the dedicated evidence workflow.

When artifacts are passed directly in a report payload, NICO parses those payload entries first. When no direct artifact payload is supplied and a GitHub token is configured, NICO can query recent GitHub Actions runs and fetch matching artifact ZIP files from authorized repositories.

## Normalized artifact fields

Each artifact is normalized into:

- `source`
- `artifact_name`
- `workflow_name`
- `timestamp`
- `status`
- `summary`
- `findings`
- `confidence`
- `missing`
- `stale`
- `affects_score`

## Status rules

- `passed`: parsed artifact contents prove the audit passed or reported zero vulnerabilities.
- `failed`: parsed artifact contents report vulnerabilities, failure, error, timeout, or cancelled state.
- `missing`: an expected artifact was not supplied or found.
- `stale`: the artifact is older than the freshness window and cannot prove current clean status.
- `unavailable`: metadata exists, but artifact content is unavailable or not classifiable.

## Scoring rules

Workflow presence alone never increases dependency or security scores.

Dependency score can improve only when parsed Python or npm artifact contents show a clean result. Failed or vulnerable artifact content lowers confidence and keeps findings visible. Missing, stale, and unavailable artifacts remain disclosed and do not prove clean status.

The CI/CD section can improve from the dedicated Audit Evidence artifact only when parsed artifact content supports a passing evidence workflow result.

## Report output

Express report packages include an `Evidence Artifacts` section with summary counts and per-artifact status. JSON report output includes `evidence_artifacts` and `evidence_artifact_summary` so frontend or downstream report renderers can display the same truth-bound evidence state.

## Human review

NICO still requires human review before client-facing delivery. Artifact parsing improves evidence quality, but it does not authorize production changes, dependency upgrades, credential rotation, deployments, or merges.
