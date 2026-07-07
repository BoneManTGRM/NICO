# Artifact Access Diagnostics

NICO can only credit GitHub Actions scanner artifacts when the deployed backend can read artifact metadata and artifact ZIP contents for the authorized repository.

## Required backend secret

Set one of these in the deployed backend environment:

- `NICO_GITHUB_TOKEN`
- `GITHUB_TOKEN`

The value is never returned by diagnostics.

## Diagnostic location

Use:

- `GET /diagnostics`

Look for:

```json
{
  "scanner_artifacts": {
    "status": "ok",
    "token_configured": true,
    "repository": "BoneManTGRM/NICO"
  }
}
```

## Status meanings

- `ok`: artifact metadata is readable and scanner artifacts can be considered for scoring.
- `token_missing`: the backend does not have `NICO_GITHUB_TOKEN` or `GITHUB_TOKEN` configured.
- `repo_unavailable`: the report did not contain a valid `owner/name` repository.
- `api_unavailable`: a token exists, but GitHub Actions metadata could not be read.

## Scoring rule

Scanner artifacts can affect section scores only when current parseable GitHub Actions artifacts are available. Missing access is shown as unavailable evidence, not treated as a pass.
