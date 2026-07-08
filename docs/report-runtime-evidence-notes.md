# Report runtime evidence notes

The Express report must not claim scanner-clean or release-ready status unless current-run artifacts prove it.

Current important distinction:

- `requirements.txt` must avoid PEP 508 extras in the package name submitted to OSV. Extras such as `PyJWT[crypto]` are valid pip syntax, but OSV package lookup must use the base package name, such as `PyJWT`, with the exact version.
- Scanner-worker evidence remains unavailable unless the hosted assessment receives an explicit scanner-worker artifact or auto-run successfully checks out the authorized repository and completes the tools.
- Workflow artifacts from GitHub Actions are not automatically attached to a hosted report unless the report flow imports them as current-run evidence.

This note exists to keep score changes evidence-bound and prevent report text from implying that CI artifacts are attached when the hosted report did not consume them.
