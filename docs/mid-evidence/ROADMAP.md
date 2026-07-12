# NICO Mid Evidence — Roadmap and Acceptance Criteria

Status: version-controlled roadmap context for human review. Completion is determined by current run evidence, not by the existence of this document.

## Priority 1 — Complete scanner evidence

- Require OSV-Scanner for every new exact-snapshot Mid and Full assessment.
- Preserve optional ecosystem-specific dependency tools.
- Require Gitleaks and TruffleHog history evidence or an exact named blocker.
- Keep Bandit and Semgrep execution, findings, failure, and timeout states distinct.
- Never infer a clean result from a missing tool.

## Priority 2 — Resolve real score blockers

- Run a new Mid assessment after deployment.
- Review every material production static finding by file and rule.
- Fix confirmed defects in small tested changes.
- Record false-positive and accepted-risk dispositions without hiding them.
- Re-run against the repaired commit and compare evidence identities.

## Priority 3 — Complete contextual evidence

- Attach architecture, deployment, QA, product, and roadmap context to the exact Mid run.
- Keep contextual documents classified as human-review evidence.
- Supply real application access for functional QA.
- Supply real native builds before any iOS or Android parity conclusion.
- Supply actual stakeholder evidence before stakeholder-alignment conclusions.

## Priority 4 — Professional report presentation

- Render unavailable categories as `NOT SCORED`.
- Remove duplicate evidence and limitation text.
- Collapse detailed evidence by default on narrow screens.
- Provide direct actions for a fresh run, evidence attachment, exception review, and Mid draft generation.
- Preserve run, snapshot, truth, review, report, approval, and delivery hash boundaries.

## Completion criteria

Issue 296 can close only when a fresh post-fix Mid run demonstrates:

1. at least one dependency scanner completed, or the exact unavailable/failed reason is named;
2. no missing scanner is represented as clean;
3. every material static finding has a disposition;
4. Gitleaks and TruffleHog report verified full-history status or exact blockers;
5. contextual evidence is attached and remains human-review-bound;
6. the Mid draft and approval request share the same run, snapshot, truth model, evidence ledger, and review packet;
7. mobile and HTML reports contain no empty score denominator or duplicated limitation text;
8. human approval remains required before client delivery.
