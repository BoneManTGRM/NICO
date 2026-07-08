# Hosted report evidence correction

The current hosted report dropped to 85/100 because a transitive dependency was pinned directly after splitting the PyJWT extra, and the exact pin produced OSV and pip-audit findings.

This correction restores the safer representation:

- Keep `PyJWT[crypto]==2.13.0` as the project requirement.
- Normalize OSV lookup to the base package name `PyJWT` and version `2.13.0`.
- Avoid direct transitive pins unless a current-run audit proves the exact version is clean.

The remaining score blockers are intentional truth-guard blockers until real artifacts are attached:

- Dependency scanner-clean artifacts are not attached.
- Static scanner-worker artifacts are not attached.
- Bandit findings require triage.
- Complexity artifacts are not attached to the hosted report.

No score is raised by this correction. It removes the accidental direct vulnerable pin that caused the 85/100 regression.
