# Mid live-status runtime

The production Mid assessment UI polls a dedicated read-only endpoint while the snapshot scanner is active:

`GET /assessment/mid-run/{run_id}/live-status`

The endpoint reads only the retained assessment record and durable scanner record. It does not recapture the repository, re-enter the assessment orchestrator, or rewrite the assessment run.

When the scanner reaches a terminal state, the response sets `continuation_required: true`. The frontend then invokes the canonical status endpoint once to continue evidence attachment, scoring, report generation, and human-review preparation.

Scanner workers persist a heartbeat every 15 seconds while a long-running tool is active. A scanner that stops updating beyond the configured recovery threshold is atomically marked `recovery_required` and remains bound to the original run, scan, snapshot, and commit identities.

Production uses two Uvicorn workers when durable Postgres is configured so status reads remain available while scanner work is active. Memory-only environments remain single-worker to preserve local in-memory identity.
