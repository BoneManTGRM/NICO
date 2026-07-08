# Sandboxed Worker Foundation

NICO hosted Express mode can inspect GitHub metadata and fetched repository files, but full static and secret scanning needs an isolated worker that checks out the authorized repository and runs language-specific analyzers.

## Goal

Provide evidence-bound scanner artifacts for these sections:

- Static Analysis: Bandit, Semgrep, ESLint, and TypeScript/typecheck evidence.
- Secrets Exposure Review: Gitleaks and TruffleHog evidence.
- Velocity / Complexity: deeper source-footprint and complexity evidence after checkout.

The worker must not mark unavailable data as clean. Missing tools remain unavailable until their artifact exists.

## Worker boundary

The hosted API should request a worker run only for authorized repositories. The worker should:

1. Create an isolated temporary workspace.
2. Check out the exact repository and commit/ref being assessed.
3. Install only the tool dependencies needed for scanning.
4. Run configured analyzers with timeouts.
5. Redact secrets before returning artifacts.
6. Return normalized JSON artifacts to the hosted assessment path.
7. Delete the workspace after the run.

## Initial analyzer set

Static tools:

- bandit for Python security findings.
- semgrep for multi-language static checks.
- eslint for frontend lint evidence.
- typescript or npm typecheck for TypeScript evidence.

Secret tools:

- gitleaks for current tree and git-history secret detection.
- trufflehog for additional git-history credential discovery.

## Artifact schema

`nico.scanner_worker.v1` is normalized by `nico/scanner_worker_artifacts.py`.

Minimum expected shape:

```json
{
  "tools": {
    "bandit": {"status": "completed", "findings": []},
    "semgrep": {"status": "completed", "findings": []},
    "eslint": {"status": "completed", "findings": []},
    "typescript": {"status": "completed", "findings": []},
    "gitleaks": {"status": "completed", "findings": []},
    "trufflehog": {"status": "completed", "findings": []}
  }
}
```

The normalizer converts that into stable counts, completed-tool lists, missing-tool lists, and report-ready evidence notes.

## Scoring rules

- Full static evidence should require all four static tools to complete.
- Full secret evidence should require both secret tools to complete.
- Findings should remain findings until fixed, suppressed with documented justification, or accepted by human review.
- A tool failure should not become a clean result; it should become unavailable data.

## Next implementation PRs

1. Add a worker execution interface and local CLI entry point.
2. Add a Git checkout adapter with allowlisted repository/ref input.
3. Add tool runners for Bandit, Semgrep, ESLint, TypeScript, Gitleaks, and TruffleHog.
4. Wire normalized artifacts into Express assessment scoring.
5. Add deployment configuration for the worker service.
