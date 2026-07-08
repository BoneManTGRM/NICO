# Hosted Scanner Artifact Integration

This layer connects explicit scanner-worker evidence to hosted Express assessment results without treating missing worker data as clean.

## Payload input

Worker-aware hosted flows can provide scanner evidence under one of these keys:

- `scanner_worker_artifact`
- `scanner_artifact`
- `worker_artifact`
- `scanner_worker`

The artifact should use the `nico.scanner_worker.v1` tool shape produced by the scanner runner layer.

## Conservative behavior

If no artifact is supplied, hosted Express results are left unchanged and an unavailable-data note is added.

If a partial artifact is supplied, completed tools are attached as evidence and missing tools remain unavailable.

If all static tools complete, the Static Analysis section may move to GREEN when findings are clean.

If both secret tools complete, the Secrets Exposure Review section may move to GREEN when findings are clean.

Velocity / Complexity may improve when full static worker evidence exists because the hosted large-footprint uncertainty is reduced.

## Entry points

- `attach_scanner_worker_artifacts(result, payload)` attaches evidence to an existing hosted result.
- `run_github_assessment_with_scanner_artifacts(payload)` runs the hosted assessment and then attaches explicit scanner-worker evidence.

Existing hosted callers can continue using `run_github_assessment` until they are ready to pass trusted worker artifacts.
