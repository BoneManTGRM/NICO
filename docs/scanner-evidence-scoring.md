# Scanner Evidence Scoring Behavior

Scanner-worker output is retained in Express reports as evidence, but the generic `scanner_worker_evidence` card is supplemental diagnostic evidence.

## Why

The core Express maturity score is based on the main assessment sections:

- Code Audit
- Dependency / Library Ecosystem
- Secrets Exposure Review
- Static Analysis
- CI/CD Analysis
- Architecture & Technical Debt
- Velocity / Complexity

A scanner-worker card can contain a mix of completed, failed, unavailable, or timed-out tools. Treating that diagnostic card as another averaged maturity section can unfairly drag the final score even after the same evidence has already been disclosed in findings and unavailable-data notes.

## Rule

`scanner_worker_evidence` is now marked:

- `supplemental: true`
- `scoring_weight: 0`
- `status: gray`
- `score_impact: diagnostic_only`

It stays visible in the report. Its findings and unavailable notes remain visible. It is not averaged into the core maturity score unless scanner results are explicitly mapped into core evidence sections.

## What still limits a 90+ score

A higher score still requires actual evidence, not cosmetic score inflation. Release-readiness and higher velocity scoring still depend on clean/complete dependency, secret, static, CI, architecture, PR traceability, and acceptance signals.
