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
- Project-aware JavaScript/TypeScript linting through eslint when project-command execution is explicitly enabled; the separately guarded image-owned static parsing mode is described below.

## Not silently enabled

Project test/build commands remain gated by `NICO_ALLOW_PROJECT_COMMANDS=true` because they execute repository-controlled scripts. Scanner Worker can still report those commands as unavailable when stronger isolation is not enabled.

## Future binaries

OSV Scanner and gitleaks/trufflehog should be added as pinned, checksummed binary installs in a later hardening pass. Until then, they must remain unavailable rather than being reported as clean.

## Trusted global ESLint source parsing

With project commands disabled, the canonical scanner can use the image-owned
nico.trusted-global-eslint.v1 profile. It verifies the existing pinned global
ESLint/parser identities and native ESLint version, then parses the complete
regular JavaScript/TypeScript source population within the existing directory
exclusions (.git, .venv, venv, node_modules, .next, dist, build, coverage,
coverage_html, and __pycache__) and 100,000-entry inventory bound. Exceeding
that bound fails closed. All suffix case variants use NICO-generated configuration.
Repository configs, plugins, local binaries, npm scripts, project preparation,
inline rule overrides, NODE_OPTIONS, and repository NODE_PATH are excluded.
Recognized Qt translation XML does not count as TypeScript source.

Raw results, source hashes, tool/config identities, per-file message counts,
native exit code, and invocation receipts remain retained. Missing, duplicate,
wrong or changed inputs, ignored/unconfigured input rows, and inconsistent native counts fail evidence completeness;
target lint findings remain valid execution evidence. Missing trusted image
prerequisites remain unavailable. This profile does not compile TypeScript,
install project dependencies, run tests/builds, or authorize delivery.
