# Dedicated assessment worker launch

The protected-main workflow `.github/workflows/assessment-worker.yml` consumes one
already-authorized durable job. Its sole dispatch input is `job_id`. Public intake
cannot choose commands, an image, a backend, a contract or worker credentials.
Automatic profile selection remains separate and inactive.

The workflow obtains GitHub OIDC directly for the existing per-job worker audience.
The backend requires the dedicated workflow path, GitHub-hosted execution, main,
and both signed release SHAs to match the serving backend. No operator session or
production-proof credential is used. If main advances beyond the serving release,
the claim fails; changing the workflow ref does not repair release alignment.

After claiming, the launcher pulls a repository-owned public GHCR image by immutable
manifest reference and checks its Docker config ID against the frozen job contract.
It then fetches the exact anonymous GitHub commit/tree and selected original bytes.
Redirects, ambient credentials, truncated trees, unsupported file types, oversized
inputs, LFS pointers and content substitutions fail before assessed-code execution.
This adapter establishes HTTPS membership and frozen SHA256 correspondence; it
does not claim local Git-object verification or whole-project coverage. Other source
providers require their own adapters. Existing isolated execution limits remain in
effect. Scheduling and provisioning consume the original enqueue deadline.

The typed `provisioning` member is included in the immutable native receipt. The
backend validates its job revision, population, sizes and image binding, retains the
original receipt in PostgreSQL, and projects the attestation under worker provenance.
Existing receipts without this member retain their prior bytes and semantics.

The backend dispatcher requests an installation token restricted to the configured
NICO repository ID and `actions:write`, using the existing GitHub App JWT signer.
There is no PAT or operator-token fallback. A durable reservation precedes HTTP.
`accepted` means GitHub accepted submission, not that execution completed. `unknown`
and abandoned `pending` reservations require provider reconciliation; repeated intake
never resubmits them automatically. A rejection is terminal for an unclaimed job.
Late dispatch responses cannot replace an active lease or a completed receipt.

Activation requires a qualified, available image and profile mapping, actual
protected-main OIDC evidence on the serving release, and existing installation
permission for Actions write on this repository. Required configuration is:

| Location | Configuration |
| --- | --- |
| GitHub repository variables | `NICO_PRODUCTION_BACKEND_URL`, `NICO_ASSESSMENT_WORKER_IMAGE` as `ghcr.io/<owner>/<repo>/assessment-cppcheck@sha256:<manifest>` |
| Backend | Existing `NICO_GITHUB_APP_ID`, `NICO_GITHUB_APP_PRIVATE_KEY`, `NICO_GITHUB_APP_INSTALLATION_ID`; `NICO_ASSESSMENT_WORKER_REPOSITORY_ID`; optional repository name override |
| Backend activation | `NICO_ASSESSMENT_WORKER_DISPATCH_ENABLED=1` only after qualification and release alignment |

The implementation does not publish an image, install an App, grant new external
permissions, set these variables or enable production selection. Those are deployment
predicates, not conclusions established by synthetic transport tests. The current
mission state and retained proof remain in `NICO-Ship-Checkpoint.md` and PR #1627.
