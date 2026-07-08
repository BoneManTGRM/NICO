# Full git-history secret scanning

NICO now distinguishes normal secret scanner completion from verified full git-history coverage.

## Goal

The Express assessment should not say full git history was scanned unless the worker actually checked out repository history and a history-aware secret scanner completed.

## Behavior

For authorized hosted scanner-worker jobs:

- NICO requests a full git checkout by default.
- Gitleaks runs as a history-aware secret scanner against the repo.
- TruffleHog runs in `git` mode against the checked-out repo URL.
- Scanner output is redacted before report attachment.
- The temporary checkout is deleted after artifact generation.

## Evidence requirements

NICO only clears the full git-history unavailable note when:

1. the request is authorized;
2. checkout metadata says `history_depth=full`;
3. checkout metadata says `full_history_secret_scan_requested=true`;
4. at least one history-aware secret scanner completes;
5. scanner output is attached through the normalized scanner artifact.

If secret scanners complete but history coverage is not verified, NICO keeps the git-history gap visible.

## Controls

- Set `NICO_ENABLE_FULL_HISTORY_SECRET_SCAN=false` to disable full-history checkout globally.
- Set request payload `full_history_secret_scan=false` to disable full-history checkout for one assessment.

## Human review

If history scanners report findings, NICO keeps human review required and the report should recommend credential rotation when a real secret is confirmed.
