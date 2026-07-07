# Score-to-85 Execution Log

## PR #39

Status: opened as a focused diagnostic PR.

Goal:

- Make scanner-artifact access visible.
- Prevent silent failure when `NICO_GITHUB_TOKEN` or `GITHUB_TOKEN` is missing.
- Add tests proving missing token state is reported and surfaced in section unavailable evidence.

Expected next action after merge:

1. Check `/diagnostics`.
2. Confirm `scanner_artifacts.status`.
3. If `token_missing`, configure the backend deployment secret and rerun the report.
4. If `ok`, inspect whether clean scanner artifacts are being credited.

## Follow-up

PR #40 should add either a real frontend lockfile or gitleaks/trufflehog artifact generation, whichever is faster to validate cleanly.
