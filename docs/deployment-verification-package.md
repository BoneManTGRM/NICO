# Deployment verification package

This update adds a deployment verification package for NICO.

## Purpose

Before trusting a fresh hosted report, NICO needs proof that the deployed backend and frontend are serving the expected current workflow surface.

## Artifact schema

`nico.deployment_verification.v1`

## Inputs

The verifier accepts caller-provided evidence such as:

- backend health payload
- targets payload
- frontend config payload
- expected main SHA
- deployed SHA

## Checks

The verifier checks:

- backend health status
- required workflow endpoint discovery
- frontend backend URL presence
- expected main SHA versus deployed SHA

## Output

The verifier returns:

- readiness score
- endpoint status
- SHA status
- missing evidence
- blockers
- next action
- human review requirement

## Boundary

This module does not call live services by itself. It evaluates supplied deployment evidence and keeps missing data explicit.
