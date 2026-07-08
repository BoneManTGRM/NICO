# Workflow preflight package

This update adds a before-run workflow preflight package.

## Purpose

The preflight package converts service catalog readiness into a concrete request package for Express, Mid, or Retainer workflows.

## Artifact schemas

The single preflight artifact is:

`nico.workflow_preflight.v1`

The batch artifact is:

`nico.workflow_preflight_batch.v1`

## Outputs

A preflight package includes:

- recommended workflow
- allowed-to-run flag
- target endpoint
- readiness score
- readiness object
- field status
- missing fields
- blockers
- request template
- approval requirements
- next action
- human-review requirement

## Boundary

Preflight only prepares a structured request package and makes missing evidence or approval requirements visible before workflow execution.
