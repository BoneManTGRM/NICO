# Six-month roadmap generator

This update adds an evidence-bound six-month roadmap generator for Mid assessments and client planning work.

## Purpose

A static roadmap is not enough for client delivery. NICO now creates a structured six-month plan from stakeholder discovery, QA and parity intake, known risks, blockers, and supplied roadmap notes.

## Artifact schema

The generator returns:

`nico.six_month_roadmap.v1`

It includes:

- roadmap status
- readiness score
- six month plan
- monthly themes
- month-level goals
- evidence basis for each month
- acceptance gate for each month
- source counts
- unavailable-data notes
- human-review requirement

## Inputs

The generator uses evidence from:

- `stakeholder_discovery`
- `qa_parity_intake`
- `roadmap_notes`
- `known_risks`
- `blockers`
- `release_blockers`
- stakeholder goals
- target users
- pain points
- constraints
- success metrics
- decision makers
- open questions

## Integration

Mid assessments now attach:

- `six_month_roadmap_artifact`
- a six-item `six_month_roadmap` summary
- generated roadmap evidence inside the Roadmap Planning section

## Safety boundary

The generator does not make final client commitments. It sequences a draft plan from available evidence. Human review and client signoff are required before pricing, scope, timeline, staffing, or delivery promises are made.
