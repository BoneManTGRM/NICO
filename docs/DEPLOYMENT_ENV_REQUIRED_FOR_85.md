# Deployment Environment Required for 85

NICO's score can remain below the 85 target even when GitHub Actions are green if the deployed backend cannot read scanner artifacts.

## Required variable

Configure one of these in the backend deployment environment:

- `NICO_GITHUB_TOKEN`
- `GITHUB_TOKEN`

## Why this matters

The report scoring path can only credit current GitHub Actions artifacts after it reads artifact metadata and downloads parseable JSON from the authorized repository.

## Verification

After deployment, open:

- `/diagnostics`

Expected scanner artifact status:

```json
"scanner_artifacts": {
  "status": "ok",
  "token_configured": true
}
```

If the status is `token_missing`, the report should show artifact access as unavailable and should not raise scanner-backed scores.
