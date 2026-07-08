# Scanner Runner Layer

This layer adds safe scanner tool execution after the worker checkout interface.

## Purpose

The worker can now represent scanner tool output without pretending missing tools are clean. Scanner runners execute tools in the checked-out repository, redact sensitive output, and return normalized artifacts for later hosted integration.

## Tool coverage

Static tools:

- Bandit
- Semgrep
- ESLint
- TypeScript typecheck

Secret tools:

- Gitleaks
- TruffleHog

## Safety behavior

- Commands use argv lists through `run_command`; no shell execution is used.
- Tool output is truncated by worker limits.
- Known secret/token shapes are redacted before artifacts are written.
- Missing executables are marked `unavailable` instead of `completed`.
- Findings remain findings until fixed, suppressed with justification, or accepted by human review.

## Next step

The next PR should wire these runner artifacts into the hosted Express assessment path behind an explicit worker-artifact input. Hosted scoring should continue to show unavailable scanner evidence unless a worker artifact exists.
