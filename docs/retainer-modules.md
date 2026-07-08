# Retainer modules

This update adds structured modules for ongoing product engineering retainer work.

## Purpose

Retainer work needs repeatable evidence, not loose weekly notes. NICO now converts ongoing delivery inputs into structured retainer signals that can support client updates, release reviews, blocker escalation, renewal conversations, and approval gates.

## Artifact schema

The module returns:

`nico.retainer_modules.v1`

It includes:

- weekly health
- monthly strategy
- release readiness
- blocker escalation
- renewal signals
- approval gates
- source counts
- unavailable-data notes
- readiness score
- human-review requirement

## Inputs

The module uses evidence from:

- `commit_summary`
- `pr_summary`
- `issue_summary`
- `blockers`
- `known_risks`
- `approval_needs`
- `release_blockers`
- `release_notes`
- `roadmap_notes`
- `client_update`
- `retainer_metrics`
- `success_metrics`

## Integration

Retainer Ops now attaches:

- `retainer_modules`
- structured weekly status actions
- structured monthly strategy focus
- structured release checklist
- approval gates
- module-backed section evidence

## Safety boundary

Retainer modules are advisory by default. Production deployment, roadmap commitments, scope changes, budget changes, timeline changes, and major dependency upgrades require human approval before client-facing commitment or execution.
