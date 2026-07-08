# Report runtime evidence fix handoff

Generated report `nico-express-BoneManTGRM-NICO(8).pdf` still scored 89/100 because the hosted report still had:

- OSV findings caused by package extras in the dependency name (`PyJWT[crypto]`).
- Missing dependency scanner-worker artifacts.
- Missing live static scanner-worker artifacts.
- Bandit findings that still need triage.

This PR fixes the extras issue by using the base package plus explicit crypto dependency:

- `PyJWT==2.13.0`
- `cryptography==46.0.3`

This PR does not fake scanner artifacts and does not force the score higher. A later report can only rise if the hosted report actually consumes clean current-run dependency/static/complexity evidence.
