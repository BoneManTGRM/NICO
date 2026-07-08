# Hosted Express metadata auth wiring

This update wires hosted Express metadata assessment to the metadata auth adapter.

## What changed

`nico.__init__` now installs the metadata wrapper for hosted assessments when the package is imported.

`nico.hosted_metadata_auth` now keeps the original hosted assessment runner and exposes:

- `run_github_assessment_with_metadata_auth`
- `install_metadata_auth_for_hosted_assessment`

## Auth behavior

Hosted Express metadata collection now prefers:

1. app installation auth
2. server-side auth
3. anonymous public metadata access

## Evidence boundary

Auth mode, evidence, and unavailable notes are recorded without exposing private credential values.

## Boundary

This remains read-only metadata collection for authorized repository assessment.
