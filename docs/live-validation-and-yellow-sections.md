# Live validation for yellow sections

The yellow sections must not be turned green by static wording changes. They become green only when Refresh Full Evidence returns current-run, report-bound worker artifacts that satisfy the existing evidence gates.

Current yellow-section blockers seen in the July 9 PDF:

- Dependency: `npm-audit` and `osv-scanner` proof still missing.
- Secrets: full-history `trufflehog` proof still missing.
- Static Analysis: `semgrep`, `eslint`, and `typescript` proof still missing; Bandit findings still require approved triage.
- Velocity / Complexity: release-readiness remains blocked until dependency/static/secret evidence and complexity proof are all attached.

This update adds visible live-validation reporting so a refreshed PDF can show whether Refresh Full Evidence actually ran, which hosted worker tools completed, and which required tools still remain missing.

The executive summary PDF paragraph is also allowed to flow instead of ending with a visible `[truncated]` marker. Dense section tables and evidence bullets remain bounded so the report stays readable.
