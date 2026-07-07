# PR39 Artifact Diagnostics Summary

This PR makes GitHub Actions artifact access a first-class diagnostic signal.

## What changes

- Missing backend token is reported as `token_missing`.
- Missing or invalid repository scope is reported as `repo_unavailable`.
- GitHub API read failure is reported as `api_unavailable`.
- Reports receive visible unavailable notes when scanner artifacts cannot be read.

## Why

Without these diagnostics, the report can remain below the score target while the reason is hidden. This PR makes the next blocker visible so follow-up work can target the real issue.
