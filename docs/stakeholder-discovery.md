# Stakeholder discovery module

This update adds structured stakeholder discovery for client audit and roadmap work.

## Purpose

Code evidence alone does not define business value. NICO now has a discovery module that turns supplied stakeholder context into report-safe business signals.

## Artifact schema

The module returns:

`nico.stakeholder_discovery.v1`

It includes:

- goals
- users
- pain points
- constraints
- success metrics
- decision makers
- open questions
- uncategorized notes
- missing categories
- roadmap inputs
- readiness score
- human-review requirement

## Inputs

The module accepts structured fields such as:

- `stakeholder_goals`
- `business_goals`
- `target_users`
- `users`
- `pain_points`
- `constraints`
- `success_metrics`
- `kpis`
- `decision_makers`
- `approvers`
- `open_questions`

It can also infer categories from free-text fields such as:

- `stakeholder_notes`
- `discovery_notes`
- `client_notes`
- `interview_notes`

## Status values

Possible statuses include:

- `needs_more_discovery`
- `ready_for_human_review_with_open_questions`
- `ready_for_human_review`

## Human review boundary

The module organizes discovery evidence. It does not decide business strategy by itself. Final roadmap commitments, pricing, client claims, and delivery decisions require human review and client signoff.

## Next integration step

A follow-up update should feed `nico.stakeholder_discovery.v1` into the six-month roadmap generator so roadmap sequencing is tied to explicit goals, pain points, constraints, and success metrics.
