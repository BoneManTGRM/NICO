# GitHub App metadata auth adapter

This update adds an auth-aware hosted metadata client adapter.

## Purpose

Hosted Express metadata collection needs the same server-side GitHub App installation auth path used by scanner checkout. The adapter lets metadata collection prefer GitHub App installation auth, then fall back to a server-side token, then anonymous access.

## Added module

`nico/hosted_metadata_auth.py`

It includes:

- `MetadataAuthGitHubAssessmentClient`
- `github_metadata_auth_summary`
- `run_github_assessment_with_metadata_auth`

## Behavior

The auth-aware client uses `build_github_auth_headers` from `nico.github_app_auth`.

Auth preference order:

1. GitHub App installation token
2. `NICO_GITHUB_TOKEN` or `GITHUB_TOKEN`
3. anonymous metadata access

## Evidence boundary

The adapter records auth mode, evidence, and unavailable notes without exposing tokens or raw secrets.

## Follow-up wiring

A follow-up update should switch the hosted Express API path from `run_github_assessment` to `run_github_assessment_with_metadata_auth`.
