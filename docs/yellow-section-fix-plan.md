# Yellow section evidence blockers

NICO must not turn yellow sections green by wording changes alone.

The current visible blockers are runtime proof gaps:

- Dependency needs current-run dependency audit artifacts.
- Secrets needs current-run full-history secret-scan artifacts.
- Static Analysis needs current-run static-analysis artifacts and approved triage for findings.
- Velocity / Complexity needs current-run complexity proof and cleared dependency/static blockers.

The fix sequence should first make the hosted report path preserve and bind the exact scanner-worker artifact produced for the report run. Score lifts remain guarded by clean evidence or approved triage.
