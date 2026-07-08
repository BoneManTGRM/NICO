# Private repository GitHub App flow

NICO private repository support must stay backend-only. The browser should never receive a GitHub token, app JWT, installation token, private key, or raw secret.

## Required server environment

Preferred GitHub App installation mode:

- `NICO_GITHUB_APP_ID`
- `NICO_GITHUB_APP_PRIVATE_KEY`
- `NICO_GITHUB_APP_INSTALLATION_ID`

Fallback server-token mode:

- `NICO_GITHUB_TOKEN`
- or `GITHUB_TOKEN`

NICO prefers GitHub App installation auth when all GitHub App values are present. If the app flow is not configured or token creation fails, NICO can fall back to a server token if one is configured. If no server credential exists, private repositories remain unavailable and the report must disclose that access gap.

## Worker checkout behavior

For hosted scanner-worker checkout, NICO uses Git `http.extraheader` environment configuration rather than embedding a token into the clone URL.

This keeps clone URLs safe for logs and report metadata:

- Clone URL remains `https://github.com/owner/repo.git`.
- Auth is passed server-side through `GIT_CONFIG_*` environment variables.
- Temporary checkout is deleted after the scanner artifact is generated.
- Checkout metadata records the auth mode, not the token.

## Read-only boundary

This flow is for authorized defensive assessment only. The GitHub App should be installed with the least privileges needed to read repository content, commits, pull requests, Actions metadata, workflow artifacts, and review history.

Do not grant write permissions unless a separate remediation workflow is explicitly designed and approval-gated.

## Report behavior

NICO may report the auth mode, such as:

- `github_app_installation`
- `server_token`
- `anonymous`

It must not report credential values.

Unavailable notes should remain visible when private repo metadata, files, PRs, Actions runs, artifacts, or review history cannot be read.
