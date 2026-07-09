# Live validation for yellow sections

The yellow sections should only turn green when NICO can prove the current report run has the required artifacts.

## Current blockers seen in the latest PDF

- Dependency is yellow because `npm-audit` and `osv-scanner` are missing from current-run scanner proof.
- Secrets is yellow because `trufflehog` and verified full-history secret coverage are missing.
- Static Analysis is yellow because live `semgrep`, `eslint`, and `typescript` scanner-worker proof is missing, and Bandit findings still require approved rule-level triage.
- Velocity / Complexity is yellow because final-clean dependency/static evidence and verified complexity evidence are not all attached.

## Live validation behavior

The Refresh Full Evidence path now records a `report_quality_guards.hosted_full_evidence_runtime` diagnostic object on every final gate pass.

Expected statuses:

- `queued`: explicit Refresh Full Evidence request was detected and required tools were missing before worker execution.
- `completed`: hosted worker returned an artifact.
- `failed_exception`: worker execution raised an exception; the error is preserved for diagnosis.
- `failed_no_artifact`: worker returned no usable artifact.
- `skipped_no_explicit_refresh_request`: normal Express report; no automatic worker run.
- `skipped_all_required_tools_already_present`: all required worker tools were already attached.

## Guardrail

NICO must not force yellow sections to green. It should make the reason visible, then turn sections green only after the exact current-run artifacts are attached and clean or formally triaged.

## PDF display fix

The executive summary is a client-facing narrative and should not end with a visible `[truncated]` marker. Dense evidence lists may still be shortened in the PDF with a pointer to Markdown/HTML.
