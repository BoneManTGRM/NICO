# Report readiness gate

This update adds `nico.report_readiness_gate.v1`.

The gate combines deployment verification, hosted smoke-test evidence, and an Express assessment request summary before a fresh client-facing report is trusted.

The gate checks:

- deployment readiness
- hosted smoke-test status
- explicit assessment authorization
- repository presence
- client name presence

The output includes status, readiness score, delivery allowed flag, missing evidence, blockers, next action, and human review requirement.
