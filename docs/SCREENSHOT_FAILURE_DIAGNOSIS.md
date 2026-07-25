# Public Assessment Failure Diagnosis

Observed public UI state:

- authorization stage completed;
- immutable run and commit identities were already assigned;
- technical and evidence-adjusted scoring had not started;
- the frontend reported `Load failed` and `assessment backend could not be reached`;
- report actions remained disabled because no final report artifact existed.

This pattern means the frontend successfully created or received a run identity but lost connectivity while continuing the backend lifecycle. It is not evidence that scoring completed, that the repository failed assessment, or that the displayed commit is invalid.

The production-resilience update addresses the application-level failure mode with bounded proxy retries, frontend retries, and status recovery. Deployment configuration and backend service health must still be verified after release.