# Hosted report evidence correction

The current hosted report remains 89/100 until runtime artifacts are consumed by the report flow.

This correction removes one false dependency finding source by avoiding extras in the OSV package name. The dependency is represented as `PyJWT==2.13.0` with `cryptography==46.0.3` instead of `PyJWT[crypto]==2.13.0`.

The remaining score blockers are intentional truth-guard blockers until real artifacts are attached:

- Dependency scanner-clean artifacts are not attached.
- Static scanner-worker artifacts are not attached.
- Bandit findings require triage.
- Complexity artifacts are not attached to the hosted report.

No score is raised by this correction.
