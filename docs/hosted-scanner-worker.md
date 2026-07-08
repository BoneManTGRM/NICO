# Hosted scanner worker activation

NICO hosted Express assessments now attempt scanner-worker execution when the request is explicitly authorized and includes an owner/repo value.

## Default hosted behavior

For `POST /assessment/github`, the browser can keep the simple Express flow:

1. Enter `owner/repo`.
2. Check the authorization box.
3. Run the assessment.

When `authorized=true` and `NICO_ENABLE_HOSTED_SCANNER_AUTORUN` is not set to `false`, NICO routes the assessment through the scanner-worker wrapper. The wrapper:

- runs the normal hosted GitHub assessment first;
- creates a temporary worker checkout of the authorized repository;
- runs available dependency, static, secret, and coverage scanner tools;
- redacts scanner output before it is attached to the report;
- removes the temporary workspace after artifact generation;
- keeps missing tools, disabled tools, checkout failures, and timeouts as unavailable evidence.

## Tool groups

Dependency tools:

- `pip-audit`
- `npm audit`
- `osv-scanner`

Static tools:

- `bandit`
- `semgrep`
- `eslint`
- `typescript`

Secret tools:

- `gitleaks`
- `trufflehog`

Coverage tools:

- `coverage`

## Full git-history secret scanning

By default, authorized hosted scanner jobs request a full git checkout for secret scanning. This allows history-aware tools to inspect past commits instead of only the current worktree.

Controls:

- `NICO_ENABLE_FULL_HISTORY_SECRET_SCAN=false` disables full-history checkout globally.
- Request payload `full_history_secret_scan=false` disables full-history checkout for a single assessment.

Evidence rules:

- NICO only clears the full git-history unavailable note when checkout metadata shows `history_depth=full` and at least one history-aware secret scanner completes.
- Gitleaks and TruffleHog outputs are redacted before they are attached to the report.
- If secret tools complete but full-history coverage is not verified, NICO keeps a visible unavailable note instead of claiming full history was scanned.

## Safety gates

Environment controls:

- `NICO_ENABLE_HOSTED_SCANNER_AUTORUN=false` disables automatic scanner-worker execution for hosted Express.
- `NICO_ENABLE_FULL_HISTORY_SECRET_SCAN=false` disables full-history checkout for secret scans.
- `NICO_ALLOW_PROJECT_COMMANDS=true` is required before project-local command tools run, including ESLint, TypeScript, and coverage. Without this flag, those tools remain disclosed as unavailable.

This keeps the one-click Express flow useful while avoiding hidden execution of project-local commands in weaker isolation environments.

## Evidence rules

NICO may raise section confidence only when worker evidence is actually complete for that section.

- Dependency score can lift when `pip-audit`, `npm audit`, and `osv-scanner` complete.
- Static score can lift when Bandit, Semgrep, ESLint, and TypeScript complete.
- Secrets score can lift when Gitleaks and TruffleHog complete and the history coverage state is disclosed.
- Full git-history secret coverage can only be claimed when checkout and scanner metadata verify it.
- Velocity/complexity can include coverage evidence when coverage runs.

Unavailable scanner tools are never treated as clean evidence. They remain visible in the report until the worker image and execution policy support them.

## Remaining limits

This update activates the hosted worker path, but it does not remove human review. A final client-facing report still needs human validation, especially when scanner findings, missing tool evidence, checkout failure, or project-command execution limits appear.
