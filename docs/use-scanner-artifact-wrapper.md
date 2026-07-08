# Hosted Endpoint Scanner Artifact Routing

`POST /assessment/github` now preserves the existing hosted Express path when no scanner-worker artifact is supplied.

When a request includes one of the supported scanner artifact keys, the endpoint routes through `run_github_assessment_with_scanner_artifacts` before the normal report post-processing chain.

Supported artifact keys:

- `scanner_worker_artifact`
- `scanner_artifact`
- `worker_artifact`
- `scanner_worker`

Empty artifact dictionaries are ignored. This prevents default empty request fields from accidentally forcing the worker-aware path.

The endpoint still does not execute scanners directly. It only attaches explicit trusted scanner-worker evidence. Missing or partial scanner data remains unavailable.
