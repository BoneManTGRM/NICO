# Report runtime evidence fix handoff

Generated report `nico-express-BoneManTGRM-NICO(9).pdf` dropped to 85/100 because `cryptography==46.0.3` was pinned directly after splitting `PyJWT[crypto]`. The hosted OSV and pip-audit evidence then reported vulnerability records for the exact `cryptography` pin.

Root correction:

- Keep `PyJWT[crypto]==2.13.0` as the installation requirement.
- Normalize package identity before OSV lookup so extras are not submitted as the OSV package name.
- Do not pin transitive crypto dependencies directly unless a current-run audit proves the exact pin is clean.

Remaining honest blockers are unchanged: dependency/static scanner-worker artifacts, Bandit triage, complexity artifacts, and human/client acceptance must be attached before final scanner-clean or client-ready claims.
