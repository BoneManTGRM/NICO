# Real 90 scoring contract v4

This release does not use 90 as an input, floor, clamp, label, or override.

Technical scoring changes are evidence-bound:

- Only verified material dependency, secret, and static-analysis findings reduce technical category scores.
- Unverified review candidates remain visible and affect assurance only.
- `completed_with_findings` is treated as completed analyzer execution when exact-commit, verification, and raw-artifact retention requirements pass.
- Missing lockfile evidence and incomplete applicable analyzers still reduce the appropriate score.
- Verified material findings remain category-specific and retain full remediation records.
- Overall maturity remains the arithmetic mean of the scored canonical sections.
- Evidence-adjusted readiness is derived from the technical score, incomplete applicable analyzers, and unresolved candidate categories.

Report-truth changes:

- Duplicate source findings are reconciled by normalized source path, function/component, and analyzer rule while preserving every source finding identifier as an alias.
- Technical and evidence-adjusted aliases are synchronized only after the technical score equals the arithmetic mean of canonical section scores.
- Real score disagreements remain blocked.
- Score-mismatch publication blocks are reconciled only after section and alias equality verification.
- Human approval remains required and client delivery remains blocked until authorization.
