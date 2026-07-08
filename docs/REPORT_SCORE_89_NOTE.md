# Why the Express report stayed at 89

The `nico-express-BoneManTGRM-NICO(8).pdf` report was still 89/100 because the hosted Express report path was still using manifest-only OSV evidence and did not attach scanner-worker runtime artifacts to that run.

The report correctly refused to claim final scanner-clean or release-ready status while these gaps remained:

- Dependency scanner artifacts were not attached for the report run.
- Static scanner artifacts were not attached for the report run.
- Bandit findings still required triage.
- Complexity artifacts were not attached for the report run.
- Client/human acceptance was not approved.

This fix addresses one false-evidence source: hosted OSV queries now normalize Python package extras before calling OSV. For example, `PyJWT[crypto]==2.13.0` is queried as package `PyJWT`, version `2.13.0`; `[crypto]` is not treated as part of the version.

This does not fake a 90+ score. The report can only move higher when real current-run scanner-worker artifacts are supplied or successfully auto-run and attached.
