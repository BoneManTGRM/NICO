# Dependency Policy

NICO dependency evidence is based on committed manifests, lockfile evidence, automated update configuration, and CI audit artifacts.

## Required evidence

- Python runtime dependencies are listed in `requirements.txt`.
- Frontend dependencies are listed in `apps/web/package.json`.
- Frontend resolved dependency evidence is committed in `apps/web/package-lock.json`.
- Package update configuration is stored in `.github/dependabot.yml`.
- CI runs Python dependency audit evidence and uploads the result as an artifact.
- CI runs frontend install, typecheck, production build, and Docker build checks.

## Review rules

- Missing lockfile evidence must stay disclosed.
- Vulnerability claims require exact package evidence or scanner output.
- Broad version-range warnings are not treated as confirmed installed-package vulnerabilities.
- Human review is required before client-final vulnerability claims.
