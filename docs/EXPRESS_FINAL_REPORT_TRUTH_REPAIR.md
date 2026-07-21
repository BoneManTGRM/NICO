# Express final report truth repair

This branch repairs two production contradictions observed on the exact deployed Express run `express_run_3e11f7aa79144b5b9005e2b9e3bd2092` at commit `b18a07fbe207625a278d154803aa39280209745f`.

## 1. Stale first-pass source scores

Express renders during an early polish pass and again after final evidence reconciliation. The evidence-specific presentation layer retained the first pass in `source_score` and reused it after the canonical section `score` changed. This produced visible contradictions such as:

- Code Audit source score `49/100` while final canonical score was `86/100`;
- Static Analysis source score `56/100` while final canonical score was `90/100`;
- source maturity `90/100` beside an evidence-adjusted score calculated from stale section baselines.

The repair refreshes every `source_score` and maturity `source_score` from the current canonical score immediately before evidence-specific presentation reconciliation. It preserves explicit deductions and human-review limits; it does not inflate scores or hide scanner exceptions.

## 2. Running and complete lifecycle states shown together

A stale active lifecycle projection could retain `truth_and_review_gates=running` while the same payload already contained complete scanner evidence, complete report artifacts, and a completed final step. The repair normalizes that terminal artifact state to:

- `status=complete`;
- `current_stage=complete`;
- `progress_percent=100`;
- all automated Express steps complete;
- `terminal_state=human_review_pending`;
- client delivery blocked pending human review.

The projection is promoted only when Markdown, HTML, PDF, scanner completion, and a completed terminal step are all present, or when the backend explicitly reports a terminal success state.

## Acceptance

- stale first-pass source scores cannot survive final reconciliation;
- Markdown, HTML, PDF, JSON, and the public UI consume the same refreshed presented scores;
- a completed Express artifact package cannot display a simultaneous running automated gate;
- scanner failures, timeouts, unavailable analyzers, and triage-required candidates remain visible;
- human review remains required and client delivery remains blocked.
