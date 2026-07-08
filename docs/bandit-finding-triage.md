# Bandit finding triage

NICO now classifies Bandit findings instead of treating the raw count as the whole truth.

## Why

A hosted Express report can show Bandit returned many findings. That number is useful, but it is not enough for a client-ready audit. Some Bandit findings are real blockers, some require human review, and some are likely false positives depending on context.

## Classification model

NICO classifies Bandit findings into:

- `real_blocker`
- `needs_human_review`
- `candidate_false_positive`

The triage model considers:

- Bandit rule ID
- Bandit severity
- Bandit confidence
- file and line location
- credential-related rules
- shell/code-execution related rules
- review-only rules that often need context

Credential rules such as hardcoded password findings are treated as blocker-level until human review confirms otherwise.

## Report behavior

When Bandit findings exist, NICO attaches a `bandit_triage` object to the Express result and adds triage evidence to the Static Analysis section.

If blocker-level findings exist, Static Analysis is capped until the finding is repaired or a human reviewer approves a security exception.

If only review-required findings exist, the section remains useful but cannot claim clean static evidence without human review.

## Human review remains required

Bandit triage is not a final security certification. It helps prioritize repair work and makes the report more honest by separating raw scanner volume from blocker-level risk.
