# QA and parity intake module

This update adds structured QA and platform-parity intake for client and app audit work.

## Purpose

A repository scan alone does not prove that a product works for users. NICO now converts supplied QA evidence and parity notes into a structured intake artifact that can support Mid assessments, mobile app reviews, and client acceptance decisions.

## Artifact schema

The module returns:

`nico.qa_parity_intake.v1`

It includes:

- QA item count
- parity item count
- platform coverage matrix
- functional-flow coverage matrix
- pass/fail/unknown/not-labeled counts
- acceptance criteria
- blockers
- unavailable-data notes
- readiness score
- human-review requirement

## Inputs

The module accepts evidence from fields such as:

- `qa_evidence`
- `qa_cases`
- `qa_notes`
- `test_results`
- `test_matrix`
- `parity_notes`
- `platform_parity`
- `device_matrix`
- `platform_matrix`
- `acceptance_criteria`
- `known_risks`
- `blockers`
- `release_blockers`

## Platforms tracked

The first version tracks evidence for:

- iOS
- Android
- web
- mobile web

## Flow categories tracked

The first version tracks:

- authentication
- onboarding
- payment or subscription
- notifications
- settings or profile
- core workflow
- error recovery

## Integration

Mid assessments now attach the `qa_parity_intake` artifact and include structured QA/parity evidence in the QA and Platform Parity sections.

## Safety boundary

The module does not claim that an app is release-ready by itself. It organizes evidence and highlights blockers. Human review and client signoff remain required before client-facing delivery or release approval.
