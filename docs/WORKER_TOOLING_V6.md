# Worker Tooling v6

This upgrade makes the hosted worker image more useful for authorized Scanner -> Express evidence collection.

## Tools added to the runtime image

The Docker image now installs the base runtime dependencies needed for repository cloning and Node/Python scanner execution:

- git
- nodejs
- npm
- eslint
- pip-audit
- bandit
- semgrep

## Tools still evidence-bound

NICO still treats every tool result as evidence-bound:

- If a tool is installed and the required manifest/source files exist, it can run.
- If a tool is missing, disabled, times out, or lacks a required manifest, the result is marked unavailable.
- Unavailable scanner evidence is not treated as a clean result.
- Human review remains required before client delivery.

## Current coverage improvement

This improves real hosted coverage for:

- Python dependency review through pip-audit when requirements.txt exists.
- Python static review through bandit when Python files exist.
- Static-analysis coverage through semgrep.
- Node dependency review through npm audit when package-lock.json exists.
- JavaScript/TypeScript linting through eslint when project-command execution is explicitly enabled.

## Not silently enabled

Project test/build commands remain gated by `NICO_ALLOW_PROJECT_COMMANDS=true` because they execute repository-controlled scripts. Scanner Worker can still report those commands as unavailable when stronger isolation is not enabled.

## Future binaries

OSV Scanner and gitleaks/trufflehog should be added as pinned, checksummed binary installs in a later hardening pass. Until then, they must remain unavailable rather than being reported as clean.
